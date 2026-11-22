"""Read-only endpoints behind the frontend's RAG Inspector page."""

from typing import Callable, Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from monitoring import Timer, recent_activity, VECTOR_COLLECTIONS, VECTOR_CHUNKS


class SearchTraceRequest(BaseModel):
    doc_id: str
    question: str
    k: int = 3


def _overlap(a: str, b: str, max_len: int = 400) -> int:
    """Length of the longest suffix of a that is a prefix of b (the splitter overlap)."""
    for n in range(min(len(a), len(b), max_len), 0, -1):
        if a[-n:] == b[:n]:
            return n
    return 0


def _chunk_position(meta: Optional[dict]) -> int:
    # Older uploads have no chunk_index; their chunk_id ends in "-<index>"
    meta = meta or {}
    if "chunk_index" in meta:
        return int(meta["chunk_index"])
    try:
        return int(str(meta.get("chunk_id", "")).rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _pca_2d(vectors: np.ndarray):
    """Project vectors to 2D. Returns (points, mean, components, explained_variance_ratio)."""
    mean = vectors.mean(axis=0)
    centered = vectors - mean
    if len(vectors) < 2:
        return np.zeros((len(vectors), 2)), mean, np.zeros((2, vectors.shape[1])), [0.0, 0.0]
    _, s, vt = np.linalg.svd(centered, full_matrices=False)
    components = vt[:2]
    if components.shape[0] < 2:
        components = np.vstack([components, np.zeros(vectors.shape[1])])
    variance = (s ** 2) / max((s ** 2).sum(), 1e-12)
    ratio = [float(variance[i]) if i < len(variance) else 0.0 for i in range(2)]
    return centered @ components.T, mean, components, ratio


def create_inspector_router(get_engine: Callable) -> APIRouter:
    router = APIRouter(prefix="/inspect", tags=["inspector"])

    def engine_or_503():
        engine = get_engine()
        if engine is None:
            raise HTTPException(status_code=503, detail="RAG_DEPENDENCIES_MISSING")
        return engine

    def collection_or_404(engine, doc_id: str):
        try:
            return engine.chroma_client.get_collection(doc_id)
        except Exception:
            raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")

    def sorted_records(collection, include):
        """Fetch records ordered by their position in the document."""
        data = collection.get(include=include)
        order = sorted(range(len(data["ids"])), key=lambda i: _chunk_position(data["metadatas"][i]))
        return data, order

    # --------------------------------------------------------
    # Overview
    # --------------------------------------------------------

    @router.get("/overview")
    async def overview():
        engine = engine_or_503()
        collections = engine.chroma_client.list_collections()

        documents = []
        for col in collections:
            meta = col.metadata or {}
            filename = meta.get("filename")
            if not filename:
                first = col.get(limit=1, include=["metadatas"])["metadatas"]
                filename = (first[0] or {}).get("filename") if first else None
            documents.append({
                "doc_id": col.name,
                "filename": filename or "(unknown)",
                "chunks": col.count(),
                "uploaded_at": meta.get("uploaded_at"),
                "domain": meta.get("domain"),
                "embed_model": meta.get("embed_model"),
                "distance": meta.get("hnsw:space", "l2"),
            })

        VECTOR_COLLECTIONS.set(len(documents))
        VECTOR_CHUNKS.set(sum(d["chunks"] for d in documents))

        embeddings = engine.embeddings
        return {
            "models": {
                "llm": engine._llm_model_name(),
                "embedding": getattr(embeddings, "model", type(embeddings).__name__),
                "query_prefix": getattr(embeddings, "query_prefix", ""),
                "document_prefix": getattr(embeddings, "doc_prefix", ""),
            },
            "splitter": {
                "chunk_size": engine.text_splitter._chunk_size,
                "chunk_overlap": engine.text_splitter._chunk_overlap,
                "separators": engine.text_splitter._separators,
            },
            "vector_store": {
                "type": type(engine.chroma_client).__name__,
                "collections": len(documents),
                "total_chunks": sum(d["chunks"] for d in documents),
            },
            "documents": sorted(documents, key=lambda d: d["uploaded_at"] or "", reverse=True),
            "activity": recent_activity(),
        }

    # --------------------------------------------------------
    # Chunks of one document
    # --------------------------------------------------------

    @router.get("/documents/{doc_id}/chunks")
    async def document_chunks(doc_id: str, dims: int = 64):
        engine = engine_or_503()
        collection = collection_or_404(engine, doc_id)
        data, order = sorted_records(collection, ["documents", "metadatas", "embeddings"])

        chunks = []
        previous_text = None
        for rank, i in enumerate(order):
            text = data["documents"][i] or ""
            meta = data["metadatas"][i] or {}
            vector = np.asarray(data["embeddings"][i], dtype=float)
            chunks.append({
                "index": rank,
                "id": data["ids"][i],
                "chunk_id": meta.get("chunk_id"),
                "page": meta.get("page"),
                "characters": len(text),
                "words": len(text.split()),
                "overlap_with_previous": _overlap(previous_text, text) if previous_text else 0,
                "text": text,
                "embedding": {
                    "dimensions": int(vector.size),
                    "norm": round(float(np.linalg.norm(vector)), 4),
                    "min": round(float(vector.min()), 4),
                    "max": round(float(vector.max()), 4),
                    "preview": [round(float(x), 4) for x in vector[:dims]],
                },
            })
            previous_text = text

        return {
            "doc_id": doc_id,
            "collection": {
                "name": collection.name,
                "id": str(collection.id),
                "metadata": collection.metadata,
            },
            "chunks": chunks,
        }

    @router.get("/documents/{doc_id}/chunks/{chunk_index}/embedding")
    async def chunk_embedding(doc_id: str, chunk_index: int):
        engine = engine_or_503()
        collection = collection_or_404(engine, doc_id)
        data, order = sorted_records(collection, ["embeddings", "metadatas"])
        if not 0 <= chunk_index < len(order):
            raise HTTPException(status_code=404, detail="CHUNK_NOT_FOUND")
        vector = data["embeddings"][order[chunk_index]]
        return {"index": chunk_index, "embedding": [round(float(x), 5) for x in vector]}

    # --------------------------------------------------------
    # 2D map of the chunk vectors (PCA)
    # --------------------------------------------------------

    @router.get("/documents/{doc_id}/projection")
    async def projection(doc_id: str, question: Optional[str] = None):
        engine = engine_or_503()
        collection = collection_or_404(engine, doc_id)
        data, order = sorted_records(collection, ["embeddings", "metadatas"])
        if not order:
            return {"points": [], "query": None, "explained_variance": [0, 0]}

        vectors = np.asarray([data["embeddings"][i] for i in order], dtype=float)
        points, mean, components, ratio = _pca_2d(vectors)

        result = {
            "points": [
                {"index": rank, "x": float(p[0]), "y": float(p[1]),
                 "page": (data["metadatas"][i] or {}).get("page")}
                for rank, (i, p) in enumerate(zip(order, points))
            ],
            "query": None,
            "explained_variance": ratio,
        }

        if question:
            q_vec = np.asarray(engine._embed_query_with_stats(question)[0], dtype=float)
            q_point = (q_vec - mean) @ components.T
            result["query"] = {"x": float(q_point[0]), "y": float(q_point[1])}

        return result

    # --------------------------------------------------------
    # Step-by-step similarity search
    # --------------------------------------------------------

    @router.post("/search")
    async def search_trace(request: SearchTraceRequest):
        engine = engine_or_503()
        collection = collection_or_404(engine, request.doc_id)
        total = collection.count()

        # 1. Embed the question (with the model's query prefix)
        q_vec, embed_stats = engine._embed_query_with_stats(request.question)
        q = np.asarray(q_vec, dtype=float)

        # 2. Ask Chroma's HNSW index for the k nearest chunks (what the app does)
        with Timer() as t_knn:
            knn = collection.query(query_embeddings=[q_vec], n_results=min(request.k, total),
                                   include=["distances"])
        top_ids = knn["ids"][0]

        # 3. For teaching: score every chunk so the ranking is visible
        with Timer() as t_all:
            data, order = sorted_records(collection, ["documents", "metadatas", "embeddings"])
        vectors = np.asarray([data["embeddings"][i] for i in order], dtype=float)
        l2_sq = ((vectors - q) ** 2).sum(axis=1)
        cosine = (vectors @ q) / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(q) + 1e-12)

        ranked = sorted(range(len(order)), key=lambda r: l2_sq[r])
        chunks = []
        for position, r in enumerate(ranked, start=1):
            i = order[r]
            meta = data["metadatas"][i] or {}
            chunks.append({
                "rank": position,
                "index": r,
                "page": meta.get("page"),
                "distance": round(float(l2_sq[r]), 4),
                "cosine_similarity": round(float(cosine[r]), 4),
                "selected": data["ids"][i] in top_ids,
                "text": data["documents"][i],
            })

        embedding_model = getattr(engine.embeddings, "model", "")
        prefix = getattr(engine.embeddings, "query_prefix", "")
        return {
            "question": request.question,
            "embedded_text": prefix + request.question,
            "embedding_model": embedding_model,
            "query_embedding": {
                "dimensions": int(q.size),
                "norm": round(float(np.linalg.norm(q)), 4),
                "preview": [round(float(x), 4) for x in q[:64]],
            },
            "timings": {
                "embed_seconds": embed_stats["seconds"],
                "embed_tokens": embed_stats.get("tokens"),
                "hnsw_search_seconds": round(t_knn.seconds, 4),
                "full_scan_seconds": round(t_all.seconds, 4),
            },
            "k": request.k,
            "total_chunks": total,
            "distance_metric": (collection.metadata or {}).get("hnsw:space", "l2"),
            "chroma_distances": [round(d, 4) for d in knn["distances"][0]],
            "chunks": chunks,
        }

    return router
