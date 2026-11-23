# ClinIQ evaluation (Ragas)

Runs a fixed set of questions through the running backend (`POST /query`, same as the
frontend) and scores the results.

## Setup (once)

```powershell
cd "C:\Users\naidu\Desktop\CLINIC 2"
py -3.11 -m venv eval\.venv
eval\.venv\Scripts\python -m pip install -r eval\requirements.txt
```

The evaluation has its own venv because Ragas needs newer `langchain-core`, `numpy` and
`openai` than the backend pins. Do not install Ragas into `cliniq-backend\.venv`.

For the judge scores, `cliniq-backend\.env` needs:

```
GROQ_API_KEY=...
RAGAS_JUDGE_MODEL=openai/gpt-oss-120b
```

## Run

Start Ollama, Chroma and the backend first, then from the repo root:

```powershell
eval\.venv\Scripts\python eval\run_eval.py                          # deterministic scores only
eval\.venv\Scripts\python eval\run_eval.py --judge                  # + Groq judge scores
eval\.venv\Scripts\python eval\run_eval.py --domains legal --judge  # one domain
eval\.venv\Scripts\python eval\run_eval.py --ids med-01,med-09      # specific questions
```

Results are written to `eval\results\<timestamp>.json` (everything, including the domain
settings used) and `.csv` (one row per question). Both folders are git-ignored.

## Scores

| Score | Judge? | Meaning | If it is low, look at |
|---|---|---|---|
| `hit_rate` | no | At least one retrieved chunk contains the evidence | embedding model, `k`, `max_distance` |
| `evidence_recall` | no | Share of evidence snippets found in the retrieved chunks | `k`, chunk size |
| `context_precision` | no | Share of retrieved chunks that contain evidence (Ragas `IDBasedContextPrecision`) | `k` too high, chunk size |
| `mrr` | no | 1 / rank of the first relevant chunk | embedding model |
| `keyword_match` | no | Share of `must_include` terms present in the answer | prompt, model |
| `correct_refusals` | no | Unanswerable questions answered with "not in the document" | prompt rules, `max_distance` |
| `false_refusals` | no | Answerable questions wrongly refused | `max_distance` too low |
| `faithfulness` | Groq | Share of answer claims supported by the retrieved chunks | prompt, model (made-up facts) |
| `answer_relevancy` | Groq | Does the answer address the question? | answer format |
| `factual_correctness` | Groq | Claim overlap between the answer and the reference answer | whole pipeline |

Judge scores are cached in `eval\.cache\` by (question, answer, chunks, judge model), so
unchanged answers are not re-graded and use no Groq tokens.

## Datasets

`eval\datasets\<domain>.jsonl`, one question per line:

```json
{"id": "leg-02", "document": "ClinIQ Privacy Policy.pdf", "question": "...",
 "reference": "the correct answer",
 "evidence": ["short exact phrase from the document"],
 "must_include": ["7"]}
```

- `document`: filename as uploaded; the newest upload with that name is used.
- `evidence`: short phrases copied exactly from the document. A chunk counts as relevant
  if it contains one. Phrases survive re-uploads and chunking changes, unlike chunk IDs.
- `must_include`: optional terms the answer must contain (numbers, names).
- `"answerable": false`: the document does not contain the answer; the app should refuse.
- `fixture`: a file in `eval\fixtures\` to upload automatically if the document is missing.
  `eval_discharge_summary.docx` is synthetic (no real patient), built by
  `fixtures\make_fixtures.py`.
