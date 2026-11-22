
import os
import re
import uuid
import time
from typing import List, Optional
from dotenv import load_dotenv

from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_chroma import Chroma
import httpx
from langchain_ollama import OllamaLLM
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.embeddings import Embeddings
from langchain_core.prompts import ChatPromptTemplate
import chromadb
from langchain_core.output_parsers import StrOutputParser

from models import Citation
from domains import (
    DEFAULT_DOMAIN, normalize_key, load_domain, get_splitter,
    build_system_prompt, add_disclaimer
)
from monitoring import (
    Timer, LLMUsageHandler, log_query, log_upload,
    EMBED_SECONDS, EMBED_TEXTS, EMBED_TOKENS, RETRIEVAL_SECONDS, RETRIEVAL_TOP_DISTANCE,
    UPLOAD_STAGE_SECONDS, UPLOAD_CHUNKS, DOCUMENTS_UPLOADED, QUERIES
)

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


class OllamaEmbedder(Embeddings):
    """Ollama /api/embed client that adds the model's query/document prefixes
    and records token counts and timings (langchain's OllamaEmbeddings drops them)."""

    def __init__(self, model: str, base_url: str, query_prefix: str = "",
                 doc_prefix: str = "", batch_size: int = 16):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
        self.batch_size = batch_size

    def embed_with_stats(self, texts: List[str], kind: str):
        prefix = self.query_prefix if kind == "query" else self.doc_prefix
        vectors, tokens, seconds = [], 0, 0.0

        for i in range(0, len(texts), self.batch_size):
            batch = [prefix + t for t in texts[i:i + self.batch_size]]
            with Timer() as t:
                resp = httpx.post(
                    f"{self.base_url}/api/embed",
                    json={"model": self.model, "input": batch},
                    timeout=600
                )
                resp.raise_for_status()
            data = resp.json()
            vectors.extend(data["embeddings"])
            tokens += data.get("prompt_eval_count", 0)
            seconds += t.seconds

        EMBED_TOKENS.labels(self.model, kind).inc(tokens)
        EMBED_TEXTS.labels(self.model, kind).inc(len(texts))
        EMBED_SECONDS.labels(self.model, kind).observe(seconds)

        return vectors, {"tokens": tokens, "seconds": round(seconds, 3), "texts": len(texts)}

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embed_with_stats(texts, "document")[0]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_with_stats([text], "query")[0][0]


class RAGEngine:
    def __init__(self):
        self.llm_provider = os.getenv("LLM_PROVIDER", "ollama")
        self.chroma_client = self._init_chroma_client()

        self.embeddings = self._init_embeddings()
        self.llm = self._init_llm()
        # Default splitter; uploads use their domain's splitter (see domains/*.json)
        self.text_splitter = get_splitter(DEFAULT_DOMAIN)

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

    def _doc_domain(self, doc_id: str, domain: Optional[str]) -> str:
        """Requested domain, else the domain the document was uploaded with."""
        if domain:
            return normalize_key(domain)
        if doc_id in self.doc_domains:
            return self.doc_domains[doc_id]
        try:
            meta = self.chroma_client.get_collection(doc_id).metadata or {}
        except Exception:
            meta = {}
        return normalize_key(meta.get("domain"))

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

            return OllamaEmbedder(
                embed_model,
                ollama_base_url,
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

    def _retrieve(self, doc_id: str, question: str, domain_key: str):
        """Embed the question once, search Chroma, and drop chunks beyond the
        domain's max_distance. Returns (docs_with_scores, stats)."""
        settings = load_domain(domain_key)["retrieval"]
        query_vector, embed_stats = self._embed_query_with_stats(question)

        with Timer() as search:
            results = self._vector_db(doc_id).similarity_search_by_vector_with_relevance_scores(
                query_vector, k=settings["k"]
            )
        RETRIEVAL_SECONDS.observe(search.seconds)
        if results:
            RETRIEVAL_TOP_DISTANCE.observe(results[0][1])

        max_distance = settings.get("max_distance")
        kept = [r for r in results if max_distance is None or r[1] <= max_distance]

        stats = {
            "domain": domain_key,
            "k": settings["k"],
            "max_distance": max_distance,
            "embed_seconds": embed_stats["seconds"],
            "embed_tokens": embed_stats["tokens"],
            "search_seconds": round(search.seconds, 4),
            "distances": [round(score, 4) for _, score in results],
            "kept": len(kept),
        }
        return kept, stats

    def _embed_query_with_stats(self, question: str):
        if isinstance(self.embeddings, OllamaEmbedder):
            vectors, stats = self.embeddings.embed_with_stats([question], "query")
            return vectors[0], stats
        with Timer() as t:
            vector = self.embeddings.embed_query(question)
        return vector, {"tokens": None, "seconds": round(t.seconds, 3)}

    def _build_prompt(self, domain_key: str) -> ChatPromptTemplate:
        system_prompt = build_system_prompt(domain_key) + "\n\nContext:\n{context}"

        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", self._human_template())
        ])

    @staticmethod
    def _chunk_label(position: int, doc) -> str:
        # PyPDF pages are 0-based; show them 1-based like a PDF viewer
        page = doc.metadata.get("page")
        return f"Chunk {position}" + (f" | page {page + 1}" if isinstance(page, int) else "")

    @classmethod
    def _format_docs(cls, docs) -> str:
        # Labels let the model cite real chunks, e.g. [Chunk 2]
        return "\n\n".join(
            f"[{cls._chunk_label(i, doc)}]\n{doc.page_content}"
            for i, doc in enumerate(docs, start=1)
        )

    @classmethod
    def _citations(cls, docs) -> List[Citation]:
        return [
            Citation(
                chunk_id=doc.metadata.get("chunk_id", ""),
                page=doc.metadata.get("page"),
                section=None,
                label=f"Chunk {i}",
                content=doc.page_content
            )
            for i, doc in enumerate(docs, start=1)
        ]

    def _llm_model_name(self) -> str:
        return getattr(self.llm, "model", None) or getattr(self.llm, "model_name", "unknown")

    def process_document(self, file_path: str, filename: str, domain: Optional[str] = 'general') -> dict:
        domain = normalize_key(domain)
        doc_id = str(uuid.uuid4())
        file_type = "pdf" if filename.lower().endswith(".pdf") else "docx"

        # Load document
        with Timer() as t_load:
            if file_type == "pdf":
                loader = PyPDFLoader(file_path)
            elif filename.lower().endswith(".docx"):
                loader = Docx2txtLoader(file_path)
            else:
                raise ValueError("Unsupported file type")
            documents = loader.load()

        # Split into chunks
        with Timer() as t_split:
            chunks = get_splitter(domain).split_documents(documents)

        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_id"] = f"{doc_id}-{i}"
            chunk.metadata["chunk_index"] = i
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["filename"] = filename
            chunk.metadata["domain"] = domain

        texts = [c.page_content for c in chunks]

        # Embed (done here rather than inside Chroma so it can be timed separately)
        if isinstance(self.embeddings, OllamaEmbedder):
            vectors, embed_stats = self.embeddings.embed_with_stats(texts, "document")
        else:
            with Timer() as t:
                vectors = self.embeddings.embed_documents(texts)
            embed_stats = {"tokens": None, "seconds": round(t.seconds, 3), "texts": len(texts)}

        # Store in ChromaDB (one collection per document)
        with Timer() as t_store:
            collection = self.chroma_client.get_or_create_collection(
                name=doc_id,
                metadata={
                    "filename": filename,
                    "domain": domain,
                    "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "embed_model": getattr(self.embeddings, "model", "unknown"),
                    "hnsw:space": "l2",
                }
            )
            if chunks:
                collection.add(
                    ids=[str(uuid.uuid4()) for _ in chunks],
                    embeddings=vectors,
                    documents=texts,
                    metadatas=[c.metadata for c in chunks]
                )

        stages = {
            "load": round(t_load.seconds, 3),
            "split": round(t_split.seconds, 3),
            "embed": embed_stats["seconds"],
            "store": round(t_store.seconds, 3),
        }
        for stage, seconds in stages.items():
            UPLOAD_STAGE_SECONDS.labels(stage).observe(seconds)
        UPLOAD_CHUNKS.observe(len(chunks))
        DOCUMENTS_UPLOADED.labels(file_type).inc()

        log_upload({
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "doc_id": doc_id,
            "filename": filename,
            "pages": len(documents),
            "characters": sum(len(d.page_content) for d in documents),
            "chunks": len(chunks),
            "domain": domain,
            "embed_tokens": embed_stats["tokens"],
            "vector_dim": len(vectors[0]) if vectors else 0,
            "stages_seconds": stages,
        })

        # Initialize session history and record domain
        self.session_histories[doc_id] = []
        self.doc_domains[doc_id] = domain

        return {
            "status": "success",
            "doc_id": doc_id,
            "filename": filename,
            "chunk_count": len(chunks)
        }

    def _log_query(self, endpoint, doc_id, question, answer, retrieval, usage, total_seconds, status="ok"):
        QUERIES.labels(endpoint, status).inc()
        log_query({
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "endpoint": endpoint,
            "status": status,
            "doc_id": doc_id,
            "question": question,
            "answer_preview": (answer or "")[:300],
            "retrieval": retrieval,
            "llm": usage,
            "total_seconds": round(total_seconds, 3),
        })

    def query(self, doc_id: str, question: str, domain: Optional[str] = None) -> dict:
        start_time = time.time()
        domain_key = self._doc_domain(doc_id, domain)

        # Retrieve once; the same chunks are the model's context and the citations
        results, retrieval = self._retrieve(doc_id, question, domain_key)
        docs = [doc for doc, _ in results]
        usage_handler = LLMUsageHandler(self._llm_model_name())

        status = "ok"
        if not docs:
            # Nothing close enough: answer without calling the model
            status = "not_found"
            answer = load_domain(domain_key)["not_found_message"]
        else:
            chain = self._build_prompt(domain_key) | self.llm | StrOutputParser()

            # Get response (handle LLM/backend errors)
            try:
                answer = self._strip_think(chain.invoke(
                    {"context": self._format_docs(docs), "input": question},
                    config={"callbacks": [usage_handler]}
                ))
            except Exception:
                import traceback
                traceback.print_exc()
                status = "llm_error"
                answer = "LLM backend unavailable — please check your LLM provider or set LLM_PROVIDER=openai and provide credentials."

        if status != "llm_error":
            answer = add_disclaimer(answer, domain_key)

        citations = self._citations(docs)

        # Update session history
        if doc_id not in self.session_histories:
            self.session_histories[doc_id] = []
        self.session_histories[doc_id].append({"role": "user", "content": question})
        self.session_histories[doc_id].append({"role": "assistant", "content": answer, "citations": [c.model_dump() for c in citations]})

        latency_ms = (time.time() - start_time) * 1000
        self._log_query("query", doc_id, question, answer, retrieval,
                        usage_handler.usage, latency_ms / 1000, status)

        return {
            "answer": answer,
            "citations": citations,
            "latency_ms": latency_ms
        }

    def query_stream(self, doc_id: str, question: str, domain: Optional[str] = None):
        """Generator that yields partial response text as produced by the LLM."""
        start_time = time.time()
        domain_key = self._doc_domain(doc_id, domain)

        results, retrieval = self._retrieve(doc_id, question, domain_key)
        docs = [doc for doc, _ in results]
        usage_handler = LLMUsageHandler(self._llm_model_name())

        if not docs:
            # Nothing close enough: answer without calling the model
            answer = add_disclaimer(load_domain(domain_key)["not_found_message"], domain_key)
            self._log_query("query_stream", doc_id, question, answer, retrieval,
                            None, time.time() - start_time, "not_found")
            yield answer
            return

        chain = self._build_prompt(domain_key) | self.llm | StrOutputParser()
        inputs = {"context": self._format_docs(docs), "input": question}
        config = {"callbacks": [usage_handler]}

        answer_parts = []
        status = "ok"
        try:
            try:
                for item in self._strip_think_stream(chain.stream(inputs, config=config)):
                    answer_parts.append(str(item))
                    yield str(item)
            except Exception:
                import traceback
                traceback.print_exc()
                if not answer_parts:
                    # Non-streaming fallback: invoke and yield in chunks (handle LLM errors)
                    try:
                        full = self._strip_think(chain.invoke(inputs, config=config))
                    except Exception:
                        traceback.print_exc()
                        status = "llm_error"
                        full = "LLM backend unavailable — please check your LLM provider or set LLM_PROVIDER=openai and provide credentials."
                    answer_parts.append(full)
                    for i in range(0, len(full), 256):
                        yield full[i:i + 256]

            if status == "ok":
                disclaimer = add_disclaimer("", domain_key)
                if disclaimer:
                    answer_parts.append(disclaimer)
                    yield disclaimer
        finally:
            self._log_query("query_stream", doc_id, question, "".join(answer_parts),
                            retrieval, usage_handler.usage, time.time() - start_time, status)

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
