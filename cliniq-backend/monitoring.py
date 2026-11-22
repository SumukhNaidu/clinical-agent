"""Prometheus metrics and an in-memory log of recent RAG activity."""

import time
import threading
from collections import deque
from typing import Optional

from langchain_core.callbacks import BaseCallbackHandler
from prometheus_client import Counter, Gauge, Histogram


# ============================================================
# PROMETHEUS METRICS
# ============================================================

HTTP_REQUESTS = Counter(
    "cliniq_http_requests_total",
    "HTTP requests handled by the API",
    ["method", "route", "status"]
)

HTTP_LATENCY = Histogram(
    "cliniq_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300)
)

LLM_TOKENS = Counter(
    "cliniq_llm_tokens_total",
    "Tokens processed by the answer model (prompt = read, completion = generated)",
    ["model", "kind"]
)

LLM_SECONDS = Histogram(
    "cliniq_llm_seconds",
    "Answer model time per call, by phase",
    ["model", "phase"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60, 120)
)

LLM_TOKENS_PER_SECOND = Histogram(
    "cliniq_llm_generation_tokens_per_second",
    "Answer model generation speed",
    ["model"],
    buckets=(1, 2, 4, 6, 8, 10, 12, 15, 20, 30, 50)
)

EMBED_TOKENS = Counter(
    "cliniq_embedding_tokens_total",
    "Tokens processed by the embedding model",
    ["model", "kind"]
)

EMBED_SECONDS = Histogram(
    "cliniq_embedding_seconds",
    "Embedding call duration",
    ["model", "kind"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120)
)

EMBED_TEXTS = Counter(
    "cliniq_embedding_texts_total",
    "Texts embedded (chunks for documents, questions for queries)",
    ["model", "kind"]
)

RETRIEVAL_SECONDS = Histogram(
    "cliniq_retrieval_seconds",
    "Vector search time in Chroma (excluding question embedding)",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2)
)

RETRIEVAL_TOP_DISTANCE = Histogram(
    "cliniq_retrieval_top_distance",
    "Distance of the best-matching chunk (lower = more similar)",
    buckets=(0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0)
)

UPLOAD_STAGE_SECONDS = Histogram(
    "cliniq_upload_stage_seconds",
    "Document processing time by stage",
    ["stage"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300)
)

UPLOAD_CHUNKS = Histogram(
    "cliniq_upload_chunks",
    "Chunks created per uploaded document",
    buckets=(1, 2, 5, 10, 20, 50, 100, 200, 500)
)

DOCUMENTS_UPLOADED = Counter(
    "cliniq_documents_uploaded_total",
    "Documents processed",
    ["file_type"]
)

QUERIES = Counter(
    "cliniq_queries_total",
    "Questions answered",
    ["endpoint", "status"]
)

VECTOR_COLLECTIONS = Gauge(
    "cliniq_vector_collections",
    "Documents (Chroma collections) in the vector store"
)

VECTOR_CHUNKS = Gauge(
    "cliniq_vector_chunks",
    "Chunks (vectors) stored across all documents"
)


# ============================================================
# RECENT ACTIVITY (for the Inspector page)
# ============================================================

_lock = threading.Lock()
RECENT_QUERIES = deque(maxlen=50)
RECENT_UPLOADS = deque(maxlen=20)


def log_query(entry: dict):
    with _lock:
        RECENT_QUERIES.appendleft(entry)


def log_upload(entry: dict):
    with _lock:
        RECENT_UPLOADS.appendleft(entry)


def recent_activity() -> dict:
    with _lock:
        return {
            "queries": list(RECENT_QUERIES),
            "uploads": list(RECENT_UPLOADS)
        }


# ============================================================
# LLM TOKEN USAGE
# ============================================================

class LLMUsageHandler(BaseCallbackHandler):
    """Records token counts and timings that Ollama returns with each answer."""

    def __init__(self, model: str):
        self.model = model
        self.usage: Optional[dict] = None

    def on_llm_end(self, response, **kwargs):
        info = {}
        try:
            info = response.generations[0][0].generation_info or {}
        except (IndexError, AttributeError):
            pass

        # OpenAI reports usage in llm_output instead
        token_usage = (response.llm_output or {}).get("token_usage") or {}

        prompt_tokens = info.get("prompt_eval_count", token_usage.get("prompt_tokens"))
        completion_tokens = info.get("eval_count", token_usage.get("completion_tokens"))

        ns = 1e9
        self.usage = {
            "model": self.model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "load_seconds": info.get("load_duration", 0) / ns if "load_duration" in info else None,
            "prompt_eval_seconds": info.get("prompt_eval_duration", 0) / ns if "prompt_eval_duration" in info else None,
            "generation_seconds": info.get("eval_duration", 0) / ns if "eval_duration" in info else None,
            "total_seconds": info.get("total_duration", 0) / ns if "total_duration" in info else None,
        }

        if prompt_tokens is not None:
            LLM_TOKENS.labels(self.model, "prompt").inc(prompt_tokens)
        if completion_tokens is not None:
            LLM_TOKENS.labels(self.model, "completion").inc(completion_tokens)

        for phase in ("load", "prompt_eval", "generation", "total"):
            seconds = self.usage[f"{phase}_seconds"]
            if seconds is not None:
                LLM_SECONDS.labels(self.model, phase).observe(seconds)

        gen_s = self.usage["generation_seconds"]
        if completion_tokens and gen_s:
            self.usage["tokens_per_second"] = round(completion_tokens / gen_s, 2)
            LLM_TOKENS_PER_SECOND.labels(self.model).observe(completion_tokens / gen_s)


class Timer:
    """with Timer() as t: ...  ->  t.seconds"""

    def __enter__(self):
        self._start = time.perf_counter()
        self.seconds = 0.0
        return self

    def __exit__(self, *exc):
        self.seconds = time.perf_counter() - self._start
        return False
