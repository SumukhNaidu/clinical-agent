"""Evaluate the ClinIQ RAG pipeline with Ragas.

The backend is called over HTTP (/query), exactly like the frontend, so this tests
the real running app. Two groups of scores:

  Deterministic (free, every run)
    hit_rate           at least one retrieved chunk contains the evidence
    evidence_recall    share of evidence snippets found in the retrieved chunks
    context_precision  share of retrieved chunks that contain evidence (Ragas IDBasedContextPrecision)
    mrr                1 / rank of the first relevant chunk
    keyword_match      share of must_include terms present in the answer
    refusal            unanswerable questions: did the app say "not in the document"?

  LLM judge (Groq, --judge)
    faithfulness, answer_relevancy, factual_correctness (Ragas)

Usage (from the repo root, backend + Chroma + Ollama running):
    eval\\.venv\\Scripts\\python eval\\run_eval.py                    # deterministic only
    eval\\.venv\\Scripts\\python eval\\run_eval.py --judge            # + Groq judge
    eval\\.venv\\Scripts\\python eval\\run_eval.py --domains medical --judge --limit 3
"""

import argparse
import asyncio
import csv
import hashlib
import json
import os
import re
import sys
import time
import warnings
from datetime import datetime
from statistics import mean

import httpx
from dotenv import dotenv_values

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATASETS_DIR = os.path.join(HERE, "datasets")
FIXTURES_DIR = os.path.join(HERE, "fixtures")
RESULTS_DIR = os.path.join(HERE, "results")
CACHE_PATH = os.path.join(HERE, ".cache", "judge_cache.json")

DETERMINISTIC_METRICS = ["hit_rate", "evidence_recall", "context_precision", "mrr", "keyword_match"]
JUDGE_METRICS = ["faithfulness", "answer_relevancy", "factual_correctness"]

# Phrases the domain prompts / not-found messages use when the document lacks the answer
REFUSAL_PATTERNS = re.compile(
    r"(not (stated|mentioned|specified|provided|given|available|included|covered|found)"
    r"|does(n't| not) (say|state|mention|contain|specify|cover|include|provide|seem to cover)"
    r"|couldn't find|could not find|no information|not in (this|the) document)",
    re.IGNORECASE,
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def strip_disclaimer(answer: str) -> str:
    # The domain disclaimer is appended by code, not claimed by the model
    return answer.split("\n\n⚠️")[0].strip()


def load_dataset(domain: str) -> list:
    with open(os.path.join(DATASETS_DIR, f"{domain}.jsonl"), encoding="utf-8") as fh:
        items = [json.loads(line) for line in fh if line.strip()]
    for item in items:
        item["domain"] = domain
        item.setdefault("answerable", True)
    return items


# ============================================================
# Backend access
# ============================================================

class Backend:
    def __init__(self, base_url: str, timeout: float):
        self.http = httpx.Client(base_url=base_url, timeout=timeout)
        self._docs = None
        self._chunks = {}

    def check(self):
        try:
            self.http.get("/health").raise_for_status()
        except Exception as e:
            sys.exit(f"Backend not reachable at {self.http.base_url} ({e}). Start it first.")

    def domains(self) -> dict:
        return {d["key"]: d for d in self.http.get("/domains").json()["domains"]}

    def overview(self) -> dict:
        return self.http.get("/inspect/overview").json()

    def find_document(self, filename: str):
        if self._docs is None:
            self._docs = self.overview()["documents"]
        # Newest upload wins when the same file was uploaded more than once
        matches = [d for d in self._docs if d["filename"] == filename]
        matches.sort(key=lambda d: d.get("uploaded_at") or "", reverse=True)
        return matches[0]["doc_id"] if matches else None

    def upload(self, path: str, domain: str) -> str:
        with open(path, "rb") as fh:
            resp = self.http.post("/upload", files={"file": (os.path.basename(path), fh)}, data={"domain": domain})
        resp.raise_for_status()
        self._docs = None
        return resp.json()["doc_id"]

    def chunks(self, doc_id: str) -> list:
        if doc_id not in self._chunks:
            self._chunks[doc_id] = self.http.get(f"/inspect/documents/{doc_id}/chunks").json()["chunks"]
        return self._chunks[doc_id]

    def query(self, doc_id: str, question: str, domain: str) -> dict:
        start = time.perf_counter()
        resp = self.http.post("/query", json={"doc_id": doc_id, "question": question, "domain": domain})
        resp.raise_for_status()
        data = resp.json()
        data["seconds"] = round(time.perf_counter() - start, 2)
        return data


def resolve_document(backend: Backend, item: dict) -> str:
    doc_id = backend.find_document(item["document"])
    if doc_id:
        return doc_id
    if item.get("fixture"):
        path = os.path.join(FIXTURES_DIR, item["fixture"])
        print(f"  uploading fixture {item['fixture']} as {item['domain']} ...")
        return backend.upload(path, item["domain"])
    raise RuntimeError(f"Document '{item['document']}' is not uploaded. Upload it in the app first.")


# ============================================================
# Deterministic metrics
# ============================================================

async def retrieval_scores(item: dict, retrieved_ids: list, chunk_text: dict) -> dict:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import IDBasedContextPrecision

    evidence = [norm(e) for e in item["evidence"]]
    # Overlapping chunks can both contain a snippet; either one counts
    relevant_ids = {cid for cid, text in chunk_text.items() if any(e in norm(text) for e in evidence)}
    retrieved_text = [norm(chunk_text.get(cid, "")) for cid in retrieved_ids]

    if not evidence:
        return {}

    found = [e for e in evidence if any(e in t for t in retrieved_text)]
    first_rank = next((i for i, cid in enumerate(retrieved_ids, 1) if cid in relevant_ids), None)

    precision = 0.0
    if retrieved_ids and relevant_ids:
        sample = SingleTurnSample(retrieved_context_ids=retrieved_ids, reference_context_ids=sorted(relevant_ids))
        precision = await IDBasedContextPrecision().single_turn_ascore(sample)

    return {
        "hit_rate": 1.0 if first_rank else 0.0,
        "evidence_recall": len(found) / len(evidence),
        "context_precision": float(precision),
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        "relevant_chunks": len(relevant_ids),
    }


def keyword_score(answer: str, terms: list):
    if not terms:
        return None
    text = norm(answer)
    return sum(norm(t) in text for t in terms) / len(terms)


def is_refusal(answer: str, citations: list) -> bool:
    return not citations or bool(REFUSAL_PATTERNS.search(answer))


# ============================================================
# LLM judge (Groq) with an on-disk cache
# ============================================================

class Judge:
    def __init__(self, env: dict):
        from openai import AsyncOpenAI
        from ragas.embeddings import OpenAIEmbeddings
        from ragas.llms import llm_factory
        from ragas.metrics.collections import AnswerRelevancy, FactualCorrectness, Faithfulness

        key = (env.get("GROQ_API_KEY") or "").strip()
        if not key:
            sys.exit("GROQ_API_KEY is missing in cliniq-backend/.env")
        self.model = (env.get("RAGAS_JUDGE_MODEL") or "openai/gpt-oss-120b").strip()

        # max_retries lets the client wait out Groq's per-minute token limit (HTTP 429)
        groq = AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", max_retries=10)
        llm = llm_factory(self.model, client=groq, temperature=0, max_tokens=4096, reasoning_effort="low")

        # Answer relevancy compares questions with embeddings: use the local Ollama model
        ollama_url = (env.get("OLLAMA_BASE_URL") or "http://localhost:11434").strip().rstrip("/")
        embed_model = (env.get("OLLAMA_EMBED_MODEL") or "hf.co/Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0").strip()
        embeddings = OpenAIEmbeddings(client=AsyncOpenAI(api_key="ollama", base_url=f"{ollama_url}/v1"),
                                      model=embed_model)

        self.metrics = {
            "faithfulness": Faithfulness(llm=llm),
            # strictness=1: one generated question instead of three, to stay inside the token limit
            "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings, strictness=1),
            "factual_correctness": FactualCorrectness(llm=llm),
        }
        self.cache = {}
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, encoding="utf-8") as fh:
                self.cache = json.load(fh)

    def _key(self, metric: str, payload: dict) -> str:
        raw = json.dumps({"metric": metric, "judge": self.model, **payload}, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def score(self, metric: str, **payload):
        key = self._key(metric, payload)
        if key in self.cache:
            return self.cache[key], True
        result = await self.metrics[metric].ascore(**payload)
        value = float(result.value) if result.value is not None else None
        self.cache[key] = value
        self._save()
        return value, False

    def _save(self):
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(self.cache, fh)


async def judge_item(judge: Judge, item: dict, answer: str, contexts: list, refused: bool) -> dict:
    scores, cached = {}, 0
    # Faithfulness: any answer that makes claims from retrieved text (also catches invented doses)
    if contexts and not refused:
        scores["faithfulness"], hit = await judge.score(
            "faithfulness", user_input=item["question"], response=answer, retrieved_contexts=contexts)
        cached += hit
    if item["answerable"]:
        scores["answer_relevancy"], hit = await judge.score(
            "answer_relevancy", user_input=item["question"], response=answer)
        cached += hit
        if item.get("reference"):
            scores["factual_correctness"], hit = await judge.score(
                "factual_correctness", response=answer, reference=item["reference"])
            cached += hit
    return scores, cached


# ============================================================
# Run
# ============================================================

def summarize(rows: list) -> dict:
    summary = {}
    for domain in sorted({r["domain"] for r in rows}):
        failed = [r for r in rows if r["domain"] == domain and r.get("error")]
        group = [r for r in rows if r["domain"] == domain and not r.get("error")]
        if not group:
            summary[domain] = {"questions": 0, "failed": len(failed)}
            continue
        answerable = [r for r in group if r["answerable"]]
        unanswerable = [r for r in group if not r["answerable"]]
        s = {"questions": len(group)}
        for m in DETERMINISTIC_METRICS + JUDGE_METRICS:
            values = [r["scores"][m] for r in group if r["scores"].get(m) is not None]
            if values:
                s[m] = round(mean(values), 3)
        if unanswerable:
            s["correct_refusals"] = f"{sum(r['refused'] for r in unanswerable)}/{len(unanswerable)}"
        if answerable:
            s["false_refusals"] = f"{sum(r['refused'] for r in answerable)}/{len(answerable)}"
        s["avg_answer_seconds"] = round(mean(r["seconds"] for r in group), 1)
        if failed:
            s["failed"] = len(failed)
        summary[domain] = s
    return summary


def print_summary(summary: dict):
    cols = DETERMINISTIC_METRICS + JUDGE_METRICS + ["correct_refusals", "false_refusals", "avg_answer_seconds", "failed"]
    print("\n" + "=" * 100)
    print(f"{'metric':<22}" + "".join(f"{d:>14}" for d in summary))
    print("-" * 100)
    for c in cols:
        if any(c in s for s in summary.values()):
            print(f"{c:<22}" + "".join(f"{str(s.get(c, '-')):>14}" for s in summary.values()))
    print("=" * 100)


def save_run(path_base: str, meta: dict, rows: list, final: bool):
    """Write results after every question so a crash or timeout loses nothing."""
    summary = summarize(rows)
    run = {**meta, "complete": final, "summary": summary, "rows": rows}
    with open(f"{path_base}.json", "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2, ensure_ascii=False)

    with open(f"{path_base}.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "domain", "answerable", "refused", "seconds"] + DETERMINISTIC_METRICS + JUDGE_METRICS
                        + ["error", "question", "answer"])
        for r in rows:
            writer.writerow([r["id"], r["domain"], r["answerable"], r.get("refused"), r.get("seconds")]
                            + [r["scores"].get(m, "") for m in DETERMINISTIC_METRICS + JUDGE_METRICS]
                            + [r.get("error", ""), r["question"], r.get("answer", "")])
    return summary


async def evaluate_item(backend: Backend, judge, item: dict, domain: str) -> dict:
    doc_id = resolve_document(backend, item)
    chunk_text = {c["chunk_id"]: c["text"] for c in backend.chunks(doc_id)}

    result = backend.query(doc_id, item["question"], domain)
    answer = strip_disclaimer(result["answer"])
    citations = result.get("citations", [])
    retrieved_ids = [c["chunk_id"] for c in citations]
    contexts = [c["content"] for c in citations]
    refused = is_refusal(answer, citations)

    scores = await retrieval_scores(item, retrieved_ids, chunk_text) if item["answerable"] else {}
    relevant_chunks = scores.pop("relevant_chunks", None)
    kw = keyword_score(answer, item.get("must_include", []))
    if kw is not None:
        scores["keyword_match"] = kw

    cached = 0
    if judge:
        judged, cached = await judge_item(judge, item, answer, contexts, refused)
        scores.update(judged)

    return {
        "id": item["id"], "domain": domain, "document": item["document"], "doc_id": doc_id,
        "question": item["question"], "answerable": item["answerable"], "refused": refused,
        "answer": answer, "reference": item.get("reference"),
        "retrieved_chunk_ids": retrieved_ids, "relevant_chunks": relevant_chunks,
        "seconds": result["seconds"], "scores": scores, "judge_cached": cached,
    }


async def main():
    parser = argparse.ArgumentParser(description="Evaluate ClinIQ with Ragas")
    parser.add_argument("--api", default="http://localhost:8005", help="backend URL")
    parser.add_argument("--domains", default="research,legal,medical", help="comma-separated dataset names")
    parser.add_argument("--judge", action="store_true", help="also run Groq LLM-judge metrics")
    parser.add_argument("--limit", type=int, default=None, help="max questions per domain")
    parser.add_argument("--ids", default=None, help="comma-separated question ids to run")
    parser.add_argument("--timeout", type=float, default=1800, help="seconds to wait for one answer")
    parser.add_argument("--resume", default=None,
                        help="results .json of an earlier run: keep its finished questions, run the rest")
    args = parser.parse_args()

    env = dotenv_values(os.path.join(ROOT, "cliniq-backend", ".env"))
    backend = Backend(args.api, args.timeout)
    backend.check()
    judge = Judge(env) if args.judge else None

    domain_config = backend.domains()
    models = backend.overview()["models"]
    wanted_ids = set(args.ids.split(",")) if args.ids else None
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]

    rows, done = [], set()
    if args.resume:
        with open(args.resume, encoding="utf-8") as fh:
            rows = [r for r in json.load(fh)["rows"] if not r.get("error")]
        done = {r["id"] for r in rows}
        path_base = os.path.splitext(args.resume)[0]
        print(f"Resuming {args.resume}: {len(done)} questions already done")
    else:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        path_base = os.path.join(RESULTS_DIR, datetime.now().strftime("%Y%m%d-%H%M%S"))

    meta = {
        "timestamp": os.path.basename(path_base),
        "judge_model": judge.model if judge else None,
        "models": models,
        "domain_settings": {d: {k: domain_config[d][k] for k in ("chunking", "retrieval")}
                            for d in domains if d in domain_config},
    }

    for domain in domains:
        items = load_dataset(domain)
        if wanted_ids:
            items = [i for i in items if i["id"] in wanted_ids]
        items = items[:args.limit] if args.limit else items
        todo = [i for i in items if i["id"] not in done]
        print(f"\n### {domain}: {len(todo)} to run ({len(items) - len(todo)} already done)")

        for item in todo:
            try:
                row = await evaluate_item(backend, judge, item, domain)
            except Exception as e:
                # Record the failure and keep going (e.g. a slow answer timing out)
                row = {"id": item["id"], "domain": domain, "document": item["document"],
                       "question": item["question"], "answerable": item["answerable"],
                       "scores": {}, "error": f"{type(e).__name__}: {e}"}
                print(f"  {item['id']:<7} FAILED  {row['error']}")
            else:
                shown = ", ".join(f"{k}={v:.2f}" for k, v in row["scores"].items() if v is not None)
                if not item["answerable"]:
                    flag = "refused ✓" if row["refused"] else "ANSWERED ✗"
                else:
                    flag = "REFUSED ✗" if row["refused"] else ""
                note = f" ({row['judge_cached']} judge scores cached)" if row["judge_cached"] else ""
                print(f"  {item['id']:<7} {row['seconds']:>5.1f}s  {flag:<11} {shown}{note}")

            rows.append(row)
            save_run(path_base, meta, rows, final=False)

    summary = save_run(path_base, meta, rows, final=True)
    print_summary(summary)
    failed = [r["id"] for r in rows if r.get("error")]
    if failed:
        print(f"\n{len(failed)} failed: {', '.join(failed)}  ->  rerun them with --resume {path_base}.json")
    print(f"\nSaved {path_base}.json\n      {path_base}.csv")


if __name__ == "__main__":
    asyncio.run(main())
