
import os
import re
import uuid
import time
from typing import List, Optional
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.embeddings import Embeddings
from langchain_core.prompts import ChatPromptTemplate
import json
import chromadb
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

from models import Citation

load_dotenv()


# (query prefix, document prefix) each embedding model was trained with
EMBED_PREFIXES = {
    "qwen3-embedding": (
        "Instruct: Given a question, retrieve passages from the document that answer the question\nQuery:",
        ""
    ),
    "nomic-embed-text": ("search_query: ", "search_document: "),
}


def _embed_family(model: str) -> Optional[str]:
    name = model.lower()
    return next((family for family in EMBED_PREFIXES if family in name), None)


class PrefixedEmbeddings(Embeddings):
    """Adds the model's query/document prefixes before embedding."""

    def __init__(self, base: Embeddings, query_prefix: str = "", doc_prefix: str = ""):
        self.base = base
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.base.embed_documents([self.doc_prefix + t for t in texts])

    def embed_query(self, text: str) -> List[float]:
        return self.base.embed_query(self.query_prefix + text)


class RAGEngine:
    def __init__(self):
        self.llm_provider = os.getenv("LLM_PROVIDER", "ollama")
        self.chroma_client = self._init_chroma_client()

        self.embeddings = self._init_embeddings()
        self.llm = self._init_llm()
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        
        self.session_histories = {}
        self.doc_domains = {}

    def _init_chroma_client(self):
        # Chroma server (CHROMA_HOST set) or embedded on-disk store as a fallback
        chroma_host = os.getenv("CHROMA_HOST")
        if chroma_host:
            return chromadb.HttpClient(
                host=chroma_host,
                port=int(os.getenv("CHROMA_PORT", "8000"))
            )

        persist_dir = os.getenv('CHROMA_PERSIST_DIR', './chroma_data')
        os.makedirs(persist_dir, exist_ok=True)
        return chromadb.PersistentClient(path=persist_dir)

    def _vector_db(self, doc_id: str) -> Chroma:
        return Chroma(
            client=self.chroma_client,
            collection_name=doc_id,
            embedding_function=self.embeddings
        )

    def _load_prompt(self, domain: str) -> str:
        domain_key = (domain or 'general').lower()
        prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        # Prefer structured JSON prompts (system + examples), fall back to plain text
        json_path = os.path.join(prompts_dir, f"{domain_key}.json")
        txt_path = os.path.join(prompts_dir, f"{domain_key}.txt")

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                system = data.get('system', '').strip()
                examples = data.get('examples', [])
                fmt = [system]
                if examples:
                    fmt.append('\nExamples:')
                    for ex in examples:
                        inp = ex.get('input')
                        out = ex.get('output')
                        if inp is not None and out is not None:
                            fmt.append(f"User: {inp}\nAssistant: {out}")
                return '\n\n'.join(fmt).strip()
            except Exception:
                pass

        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r', encoding='utf-8') as fh:
                    return fh.read().strip()
            except Exception:
                pass

        # ultimate fallback
        return "You are a helpful document assistant. Answer the user's question based only on the provided context." 

    def _init_embeddings(self):
        if self.llm_provider == "openai":
            return OpenAIEmbeddings(model="text-embedding-3-small")
        else:
            ollama_base_url = os.getenv(
                "OLLAMA_BASE_URL",
                "http://localhost:11434"
            )

            embed_model = os.getenv(
                "OLLAMA_EMBED_MODEL",
                "hf.co/Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"
            )

            return PrefixedEmbeddings(
                OllamaEmbeddings(
                    model=embed_model,
                    base_url=ollama_base_url
                ),
                *EMBED_PREFIXES.get(_embed_family(embed_model), ("", ""))
            )

    def _init_llm(self):
        if self.llm_provider == "openai":
            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0
            )
        else:
            ollama_base_url = os.getenv(
                "OLLAMA_BASE_URL",
                "http://localhost:11434"
            )

            # Default is Qwen3-4B (HF GGUF, Q4_K_M), built from ollama/Modelfile
            return OllamaLLM(
                model=os.getenv("OLLAMA_MODEL", "qwen3-4b-nothink"),
                temperature=0,
                base_url=ollama_base_url
            )

    def _human_template(self) -> str:
        # Qwen3 soft switch: "/no_think" in the user turn disables reasoning
        if self.llm_provider == "openai":
            return "{input}"
        return "{input} /no_think"

    @staticmethod
    def _strip_think(text: str) -> str:
        return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).lstrip()

    @staticmethod
    def _strip_think_stream(stream):
        """Drop a leading <think>...</think> block from a token stream."""
        buffer = ""
        passthrough = False
        started = False  # skip whitespace between </think> and the answer
        for item in stream:
            if passthrough:
                if not started:
                    item = str(item).lstrip()
                    if not item:
                        continue
                    started = True
                yield item
                continue
            buffer += str(item)
            stripped = buffer.lstrip()
            if "<think>".startswith(stripped) or (stripped.startswith("<think>") and "</think>" not in stripped):
                continue  # still inside (or possibly starting) a think block
            passthrough = True
            rest = RAGEngine._strip_think(buffer)
            if rest:
                started = True
                yield rest
        if not passthrough and buffer:
            rest = RAGEngine._strip_think(buffer)
            if rest:
                yield rest

    def process_document(self, file_path: str, filename: str, domain: Optional[str] = 'general') -> dict:
        def _safe_domain(d):
            return (d or 'general').lower()
        doc_id = str(uuid.uuid4())
        
        # Load document
        if filename.lower().endswith(".pdf"):
            loader = PyPDFLoader(file_path)
        elif filename.lower().endswith(".docx"):
            loader = Docx2txtLoader(file_path)
        else:
            raise ValueError("Unsupported file type")
            
        documents = loader.load()
        
        # Split into chunks
        chunks = self.text_splitter.split_documents(documents)
        
        # Add metadata to chunks
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_id"] = f"{doc_id}-{i}"
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["filename"] = filename
            # keep domain if provided by caller
            chunk.metadata["domain"] = _safe_domain(domain)
        
        # Store in ChromaDB
        vector_db = self._vector_db(doc_id)
        vector_db.add_documents(chunks)
        
        # Initialize session history and record domain
        self.session_histories[doc_id] = []
        self.doc_domains[doc_id] = _safe_domain(domain)
        
        return {
            "status": "success",
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": len(chunks)
        }

    def query(self, doc_id: str, question: str, domain: Optional[str] = None) -> dict:
        def _safe_domain(d):
            return (d or 'general').lower()
        start_time = time.time()
        
        # Load vector DB for this doc
        vector_db = self._vector_db(doc_id)
        retriever = vector_db.as_retriever(search_kwargs={"k": 3})
        
        # Retrieve relevant docs first
        docs = retriever.invoke(question)
        
        # Create RAG chain
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        # Select system prompt based on provided domain, document domain, or default
        if domain:
            domain_key = _safe_domain(domain)
        else:
            domain_key = self.doc_domains.get(doc_id, 'general')

        prompt_text = self._load_prompt(domain_key)
        system_prompt = prompt_text + "\n\nContext: {context}"

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._human_template())
        ])

        # Reuse the docs retrieved above as context (avoids a second search)
        chain = prompt | self.llm | StrOutputParser()

        # Get response (handle LLM/backend errors)
        try:
            answer = self._strip_think(chain.invoke({
                "context": format_docs(docs),
                "input": question
            }))
        except Exception:
            import traceback
            traceback.print_exc()
            answer = "LLM backend unavailable — please check your LLM provider or set LLM_PROVIDER=openai and provide credentials."
        
        # Process citations
        citations = []
        for doc in docs:
            citation = Citation(
                chunk_id=doc.metadata.get("chunk_id", ""),
                page=doc.metadata.get("page"),
                section=None,
                content=doc.page_content
            )
            citations.append(citation)
        
        # Update session history
        if doc_id not in self.session_histories:
            self.session_histories[doc_id] = []
        self.session_histories[doc_id].append({"role": "user", "content": question})
        self.session_histories[doc_id].append({"role": "assistant", "content": answer, "citations": [c.model_dump() for c in citations]})
        
        latency_ms = (time.time() - start_time) * 1000
        
        return {
            "answer": answer,
            "citations": citations,
            "latency_ms": latency_ms
        }

    def query_stream(self, doc_id: str, question: str, domain: Optional[str] = None):
        """Generator that yields partial response text as produced by the LLM.

        Best-effort streaming: if the composed runnable `chain` supports a
        `.stream()` method it will be used to yield token deltas. Otherwise
        the full answer is produced and emitted in chunked pieces as a
        graceful fallback.
        """
        def _safe_domain(d):
            return (d or 'general').lower()

        # Load vector DB for this doc
        vector_db = self._vector_db(doc_id)
        retriever = vector_db.as_retriever(search_kwargs={"k": 3})

        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        if domain:
            domain_key = _safe_domain(domain)
        else:
            domain_key = self.doc_domains.get(doc_id, 'general')

        prompt_text = self._load_prompt(domain_key)
        system_prompt = prompt_text + "\n\nContext: {context}"

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._human_template())
        ])

        chain = (
            {"context": retriever | format_docs, "input": RunnablePassthrough()}
            | prompt
            | self.llm
            | StrOutputParser()
        )

        # Try to stream from the chain if it supports streaming
        try:
            stream_iter = self._strip_think_stream(chain.stream(question))
            for item in stream_iter:
                # Item may be a string delta or object; normalize to string
                try:
                    yield str(item)
                except Exception:
                    yield json.dumps(item)
            return
        except Exception:
            import traceback
            traceback.print_exc()
            # Fall back to non-streaming invoke
            pass

        # Non-streaming fallback: invoke and yield in chunks (handle LLM errors)
        try:
            full = self._strip_think(chain.invoke(question))
        except Exception:
            import traceback
            traceback.print_exc()
            full = "LLM backend unavailable — please check your LLM provider or set LLM_PROVIDER=openai and provide credentials."

        chunk_size = 256
        for i in range(0, len(full), chunk_size):
            yield full[i:i+chunk_size]

    def get_session_history(self, doc_id: str) -> List[dict]:
        return self.session_histories.get(doc_id, [])

    def delete_document(self, doc_id: str) -> dict:
        # Delete ChromaDB collection
        try:
            self.chroma_client.delete_collection(doc_id)
        except ValueError:
            pass  # Collection doesn't exist
            
        # Clear session history
        if doc_id in self.session_histories:
            del self.session_histories[doc_id]
            
        return {"status": "deleted"}
