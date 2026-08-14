# ClinIQ – AI-Powered Document Intelligence Platform

ClinIQ is a Retrieval-Augmented Generation (RAG) based document intelligence platform that allows users to upload PDF and DOCX documents and interact with them using natural-language questions.

The system processes uploaded documents into chunks, stores their vector representations in ChromaDB, retrieves the most relevant content for each question, and uses a locally hosted Ollama LLM to generate grounded responses with page-level source references.

## Features

- PDF and DOCX document upload
- Automatic document chunking
- Vector-based semantic retrieval
- ChromaDB vector database
- Retrieval-Augmented Generation (RAG)
- Local LLM inference using Ollama
- Natural-language document querying
- Page-level source citations
- Streaming responses
- Document session history
- Document deletion
- FastAPI REST API
- React-based web interface
- CORS-enabled API
- Public demo through ngrok

## Tech Stack

### Frontend
- React
- Vite
- JavaScript
- CSS

### Backend
- Python
- FastAPI
- Uvicorn

### AI / RAG
- Ollama
- Qwen 2.5 1.5B
- ChromaDB
- Embeddings
- Retrieval-Augmented Generation

### Document Processing
- PDF processing
- DOCX processing
- Text chunking

### Deployment / Networking
- Docker
- Render
- ngrok

## System Architecture

User
↓
React Frontend
↓
FastAPI Backend
↓
Document Processing
↓
Text Chunking
↓
Embeddings
↓
ChromaDB
↓
Semantic Retrieval
↓
Ollama / Qwen 2.5
↓
Grounded Response
↓
Source References

## How It Works

### 1. Document Upload

The user uploads a PDF or DOCX document.

The backend validates:

- File type
- File size
- Document format

The document is temporarily stored and passed to the RAG engine.

### 2. Document Processing

The document is extracted and divided into smaller chunks.

Each chunk is converted into an embedding representation.

### 3. Vector Storage

The embeddings are stored in ChromaDB.

This allows the system to perform semantic similarity searches instead of relying only on keyword matching.

### 4. User Query

The user asks a question about the uploaded document.

For example:

"Summarize the main security risks."

### 5. Retrieval

ClinIQ searches the vector database and retrieves the most relevant document chunks.

### 6. LLM Generation

The retrieved context is provided to the locally hosted Ollama model.

The model generates an answer based on the retrieved document content.

### 7. Source Grounding

The application returns source references associated with the retrieved content.

Example:

[p. 1] [p. 3] [p. 7]

This makes the generated response easier to verify against the original document.

## API Endpoints

### Health Check

GET /health

Checks whether the backend is running.

### Upload Document

POST /upload

Uploads and processes a PDF or DOCX document.

### Query Document

POST /query

Sends a question about an uploaded document.

### Streaming Query

POST /query/stream

Streams the generated response to the frontend.

### Session History

GET /sessions/{doc_id}

Retrieves conversation history for a document.

### Delete Document

DELETE /document/{doc_id}

Deletes a processed document and its associated data.

## Local Setup

### Clone Repository

git clone <your-repository-url>

cd clinical-agent

### Backend

cd cliniq-backend

Create a virtual environment:

python -m venv .venv

Activate it on Windows:

.venv\Scripts\activate

Install dependencies:

pip install -r requirements.txt

Start the API:

python -m uvicorn api:app --host 127.0.0.1 --port 8005

### Ollama

Install Ollama and make sure the Ollama service is running.

Pull the required models:

ollama pull qwen2.5:1.5b

ollama pull nomic-embed-text

Verify:

curl http://localhost:11434/api/tags

### Frontend

cd cliniq-frontend

Install dependencies:

npm install

Start the development server:

npm run dev -- --port 3001

The application will be available at:

http://localhost:3001

## RAG Pipeline

The core pipeline is:

Document
→ Text Extraction
→ Chunking
→ Embeddings
→ ChromaDB
→ Similarity Search
→ Relevant Context
→ Ollama LLM
→ Grounded Response

## Example

A user uploads:

Cyber Security Lab Manual.pdf

The document is processed into multiple chunks.

The user asks:

"Brief me about this document."

ClinIQ retrieves relevant sections and generates a concise response with page references.

## Why RAG?

Instead of sending an entire document directly to the language model, ClinIQ retrieves only the most relevant sections.

This helps:

- Reduce unnecessary context
- Improve relevance
- Ground responses in source documents
- Support larger documents
- Provide traceable references

## Project Highlights

- Built an end-to-end RAG application
- Integrated a local LLM using Ollama
- Implemented vector similarity search
- Built REST APIs using FastAPI
- Developed a React-based document interface
- Implemented source-aware document responses
- Added streaming query support
- Exposed the application through a public development tunnel

## Future Improvements

- Authentication and user accounts
- Persistent cloud vector storage
- Production LLM hosting
- Multi-user document isolation
- Better document management
- Conversation export
- Production cloud deployment
- Monitoring and analytics

## Author

Sumukh Naidu

B.Tech – Information Science and Engineering