
# ClinIQ - Document Intelligence Platform

ClinIQ is a RAG-powered document intelligence demo built with FastAPI (backend), React + Vite (frontend), ChromaDB, and LangChain. The project is domain-agnostic and can be used with any collection of documents (research papers, contracts, reports, finance, etc.).

## Features

- 📄 **Document Upload**: Support for PDF and DOCX files
- 🤖 **RAG Q&A**: Ask questions about uploaded documents
- 🔍 **Citation System**: Verifiable source citations for every answer
- 📜 **Session History**: Chat history per document
- 🎨 **Dark Theme**: Professional dark mode interface
- 🔌 **LLM Switching**: Support for both Ollama (local) and OpenAI (cloud)

## Tech Stack

- **Frontend**: React + Vite
- **Backend**: FastAPI
- **Vector DB**: ChromaDB (persistent)
- **Orchestration**: LangChain
- **LLM Support**: Ollama (qwen2.5:1.5b) or OpenAI (GPT-4o-mini)
- **Embeddings**: nomic-embed-text (Ollama) or text-embedding-3-small (OpenAI)

## Project Structure

```
CLINIC 2/
├── cliniq-backend/
│   ├── api.py          # FastAPI entry point
│   ├── rag_engine.py   # RAG logic and document processing
│   ├── models.py       # Pydantic models
│   ├── requirements.txt
│   └── .env
└── cliniq-frontend/
    ├── src/
    │   ├── components/ # React components
    │   ├── api/        # API client
    │   ├── App.jsx
    │   └── main.jsx
    ├── package.json
    └── .env
```

## Getting Started

### Prerequisites

1. Python 3.10+ (recommended to use a Conda environment on Windows for heavy ML deps)
2. Node.js 18+
3. Ollama (optional, if using a local LLM)

### Backend Setup

There are two common ways to run the backend on Windows: (A) Conda (recommended for heavy packages) or (B) pip/venv.

A) Conda (recommended on Windows)

```powershell
cd cliniq-backend
conda create -n cliniq python=3.10 -y
conda activate cliniq
# Install pip and build tools, then install Python deps (prefer binary builds on conda-forge if you run into build errors):
pip install -r requirements.txt
```

Run the backend with the Conda interpreter (example port 8005):

```powershell
conda run -n cliniq --no-capture-output python -m uvicorn api:app --host 127.0.0.1 --port 8005
```

B) venv + pip (cross-platform)

```bash
cd cliniq-backend
python -m venv venv
source venv/bin/activate   # macOS/Linux
.\venv\Scripts\activate  # Windows PowerShell
pip install -r requirements.txt
python -m uvicorn api:app --host 127.0.0.1 --port 8005
```

Notes:
- If you plan to use Ollama (local LLMs), install and pull models via `ollama` as needed.
- The backend supports lazy-loading of heavy RAG dependencies; the `/health` endpoint works even when heavy deps are not installed.

### Frontend Setup

```bash
cd cliniq-frontend
npm install
```

Copy and edit `.env.example` to `.env` (or set env vars in your shell). Key values:

- `VITE_API_URL` — base URL for the backend API (e.g. `http://127.0.0.1:8005`)
- `VITE_DOMAIN` — optional domain key used to select prompt templates (`general`, `legal`, `finance`, etc.)

Example (PowerShell):

```powershell
cd cliniq-frontend
copy .env.example .env
set VITE_API_URL=http://127.0.0.1:8005
set VITE_DOMAIN=general
npm run dev
```

The dev server typically runs on `http://localhost:3000` (or the port shown by Vite).

## Usage

1. Open your browser and go to the frontend dev server (e.g. `http://localhost:3000`).
2. Upload a document (PDF or DOCX).
3. Wait for processing — the document is parsed, chunked, and indexed in ChromaDB.
4. Ask questions about your document using the chat UI.
5. Click citations to see source text and verify provenance.

## API Endpoints

- `POST /upload` - Upload and process a document
- `POST /query` - Query a document
- `GET /sessions/{doc_id}` - Get chat history
- `DELETE /document/{doc_id}` - Delete a document's data
- `GET /health` - Health check

## Notes & Next Steps

- The codebase includes work to make the UI and prompts domain-agnostic. To add domain-specific behavior, provide prompt templates in the backend and set `DOMAIN` in the frontend `.env`.
- On Windows, prefer Conda for installing heavy ML dependencies (NumPy, PyTorch, etc.) using `conda-forge` binary builds.

If you'd like, I can:

- Add a visible domain selector to the frontend and wire it to per-domain prompt templates.
- Add a `prompts/` folder with example templates for `general`, `legal`, and `finance`.

## License

MIT
