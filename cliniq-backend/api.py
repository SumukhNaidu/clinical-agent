
import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from models import UploadResponse, QueryRequest, QueryResponse, SessionHistory
from fastapi.responses import StreamingResponse
import json

load_dotenv()

app = FastAPI(title="ClinIQ API")
# Lazily instantiate RAGEngine so the API can run without heavy ML deps
rag_engine = None

def get_rag_engine():
    global rag_engine
    if rag_engine is None:
        try:
            from rag_engine import RAGEngine
            rag_engine = RAGEngine()
        except Exception:
            return None
    return rag_engine

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create temp directory for uploads
os.makedirs("./temp_uploads", exist_ok=True)


@app.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...), domain: str = Form('general')):
    # Validate file type
    if not (file.filename.lower().endswith(".pdf") or file.filename.lower().endswith(".docx")):
        raise HTTPException(status_code=400, detail="INVALID_FILE_TYPE")
        
    # Validate file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > 25 * 1024 * 1024:  # 25 MB
        raise HTTPException(status_code=400, detail="FILE_TOO_LARGE")
        
    # Save temp file
    temp_path = f"./temp_uploads/{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Process with RAG engine
    engine = get_rag_engine()
    if engine is None:
        # Missing heavy dependencies (langchain/chromadb/etc.)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=503, detail="RAG_DEPENDENCIES_MISSING")
    try:
        result = engine.process_document(temp_path, file.filename, domain=domain)
        return UploadResponse(**result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="PROCESSING_ERROR")
    finally:
        # Clean up temp file. On Windows the PDF parser may still hold a handle
        # to the file after an error, causing PermissionError on remove. Ignore
        # PermissionError to avoid crashing the request handler; the file will
        # be removed on the next run or by external cleanup.
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except PermissionError:
                pass


@app.post("/query", response_model=QueryResponse)
async def query_document(request: QueryRequest):
    engine = get_rag_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="RAG_DEPENDENCIES_MISSING")
    try:
        domain = getattr(request, 'domain', 'general')
        result = engine.query(request.doc_id, request.question, domain=domain)
        return QueryResponse(**result)
    except ValueError as e:
        if "Collection" in str(e):
            raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")
        else:
            raise HTTPException(status_code=500, detail="PROCESSING_ERROR")
    except Exception:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail="LLM_UNAVAILABLE")


@app.post("/query/stream")
async def query_document_stream(request: QueryRequest):
    engine = get_rag_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="RAG_DEPENDENCIES_MISSING")

    try:
        domain = getattr(request, 'domain', 'general')

        def event_generator():
            try:
                for chunk in engine.query_stream(request.doc_id, request.question, domain=domain):
                    # send raw text chunks; the frontend will append
                    if isinstance(chunk, (dict, list)):
                        data = json.dumps(chunk)
                    else:
                        data = str(chunk)
                    yield data
                # final marker (optional)
                yield "__DONE__"
            except ValueError as e:
                # propagate doc not found as a final error token
                yield json.dumps({"error": "DOC_NOT_FOUND"})
            except Exception:
                import traceback
                traceback.print_exc()
                yield json.dumps({"error": "LLM_ERROR"})

        return StreamingResponse(event_generator(), media_type='text/plain')
    except ValueError as e:
        if "Collection" in str(e):
            raise HTTPException(status_code=404, detail="DOC_NOT_FOUND")
        else:
            raise HTTPException(status_code=500, detail="PROCESSING_ERROR")
    except Exception:
        raise HTTPException(status_code=503, detail="LLM_UNAVAILABLE")


@app.get("/sessions/{doc_id}", response_model=SessionHistory)
async def get_session(doc_id: str):
    engine = get_rag_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="RAG_DEPENDENCIES_MISSING")
    history = engine.get_session_history(doc_id)
    return SessionHistory(history=history)


@app.delete("/document/{doc_id}")
async def delete_document(doc_id: str):
    engine = get_rag_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="RAG_DEPENDENCIES_MISSING")
    result = engine.delete_document(doc_id)
    return result


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
