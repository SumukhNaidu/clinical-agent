import os
import shutil
import json
import traceback

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from models import UploadResponse, QueryRequest, QueryResponse, SessionHistory


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(title="ClinIQ API")


# ============================================================
# RAG ENGINE
# ============================================================

# Lazily instantiate RAGEngine.
# This allows the API to start even if heavy ML dependencies
# are not loaded until an actual RAG operation is requested.

rag_engine = None


def get_rag_engine():
    global rag_engine

    if rag_engine is None:
        try:
            print("========== INITIALIZING RAG ENGINE ==========")

            from rag_engine import RAGEngine

            rag_engine = RAGEngine()

            print("========== RAG ENGINE INITIALIZED ==========")

        except Exception as e:
            print("========== RAG ENGINE INITIALIZATION ERROR ==========")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            traceback.print_exc()
            print("======================================================")

            return None

    return rag_engine


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# TEMP UPLOAD DIRECTORY
# ============================================================

os.makedirs("./temp_uploads", exist_ok=True)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
async def root():
    return {
        "message": "ClinIQ API is running",
        "docs": "/docs",
        "health": "/health"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health_check():
    return {
        "status": "ok"
    }


# ============================================================
# UPLOAD DOCUMENT
# ============================================================

@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    domain: str = Form("general")
):

    print("========== UPLOAD REQUEST RECEIVED ==========")
    print(f"Filename: {file.filename}")
    print(f"Domain: {domain}")

    # --------------------------------------------------------
    # Validate filename
    # --------------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="INVALID_FILE_NAME"
        )

    filename_lower = file.filename.lower()

    # --------------------------------------------------------
    # Validate file type
    # --------------------------------------------------------

    if not (
        filename_lower.endswith(".pdf")
        or filename_lower.endswith(".docx")
    ):
        raise HTTPException(
            status_code=400,
            detail="INVALID_FILE_TYPE"
        )

    # --------------------------------------------------------
    # Validate file size
    # --------------------------------------------------------

    try:
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        print(f"File size: {file_size} bytes")

    except Exception as e:
        print("========== FILE SIZE CHECK ERROR ==========")
        print(f"Error: {str(e)}")
        traceback.print_exc()

        raise HTTPException(
            status_code=400,
            detail="FILE_SIZE_CHECK_FAILED"
        )

    if file_size > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="FILE_TOO_LARGE"
        )

    # --------------------------------------------------------
    # Create safe temporary filename
    # --------------------------------------------------------

    safe_filename = os.path.basename(file.filename)

    temp_path = os.path.join(
        "./temp_uploads",
        safe_filename
    )

    print(f"Temporary file path: {temp_path}")

    # --------------------------------------------------------
    # Save uploaded file
    # --------------------------------------------------------

    try:

        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer
            )

        print("File successfully saved.")

    except Exception as e:

        print("========== FILE SAVE ERROR ==========")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="FILE_SAVE_ERROR"
        )

    # --------------------------------------------------------
    # Get RAG engine
    # --------------------------------------------------------

    engine = get_rag_engine()

    if engine is None:

        print("RAG engine could not be initialized.")

        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

        raise HTTPException(
            status_code=503,
            detail="RAG_DEPENDENCIES_MISSING"
        )

    # --------------------------------------------------------
    # Process document
    # --------------------------------------------------------

    try:

        print("========== STARTING DOCUMENT PROCESSING ==========")
        print(f"Processing: {safe_filename}")
        print(f"Domain: {domain}")

        result = engine.process_document(
            temp_path,
            safe_filename,
            domain=domain
        )

        print("========== DOCUMENT PROCESSING SUCCESS ==========")
        print(f"Result: {result}")

        return UploadResponse(**result)

    except Exception as e:

        print("========== UPLOAD PROCESSING ERROR ==========")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("---------- FULL TRACEBACK ----------")

        traceback.print_exc()

        print("==============================================")

        # IMPORTANT:
        # We expose the actual error temporarily so that
        # Render logs and Swagger show what is failing.

        raise HTTPException(
            status_code=500,
            detail=(
                f"PROCESSING_ERROR: "
                f"{type(e).__name__}: "
                f"{str(e)}"
            )
        )

    finally:

        # ----------------------------------------------------
        # Clean temporary file
        # ----------------------------------------------------

        if os.path.exists(temp_path):

            try:

                os.remove(temp_path)

                print(
                    f"Temporary file removed: {temp_path}"
                )

            except PermissionError:

                print(
                    "Could not remove temporary file "
                    "because it is still being used."
                )

            except Exception as e:

                print(
                    f"Temporary file cleanup failed: {str(e)}"
                )


# ============================================================
# QUERY DOCUMENT
# ============================================================

@app.post("/query", response_model=QueryResponse)
async def query_document(request: QueryRequest):

    print("========== QUERY REQUEST ==========")
    print(f"Document ID: {request.doc_id}")
    print(f"Question: {request.question}")

    engine = get_rag_engine()

    if engine is None:

        raise HTTPException(
            status_code=503,
            detail="RAG_DEPENDENCIES_MISSING"
        )

    try:

        domain = getattr(
            request,
            "domain",
            "general"
        )

        result = engine.query(
            request.doc_id,
            request.question,
            domain=domain
        )

        return QueryResponse(**result)

    except ValueError as e:

        print("========== QUERY VALUE ERROR ==========")
        print(str(e))

        if "Collection" in str(e):

            raise HTTPException(
                status_code=404,
                detail="DOC_NOT_FOUND"
            )

        raise HTTPException(
            status_code=500,
            detail="PROCESSING_ERROR"
        )

    except Exception as e:

        print("========== QUERY ERROR ==========")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        traceback.print_exc()

        raise HTTPException(
            status_code=503,
            detail="LLM_UNAVAILABLE"
        )


# ============================================================
# STREAMING QUERY
# ============================================================

@app.post("/query/stream")
async def query_document_stream(
    request: QueryRequest
):

    print("========== STREAM QUERY REQUEST ==========")
    print(f"Document ID: {request.doc_id}")
    print(f"Question: {request.question}")

    engine = get_rag_engine()

    if engine is None:

        raise HTTPException(
            status_code=503,
            detail="RAG_DEPENDENCIES_MISSING"
        )

    try:

        domain = getattr(
            request,
            "domain",
            "general"
        )

        def event_generator():

            try:

                for chunk in engine.query_stream(
                    request.doc_id,
                    request.question,
                    domain=domain
                ):

                    if isinstance(
                        chunk,
                        (dict, list)
                    ):
                        data = json.dumps(chunk)

                    else:
                        data = str(chunk)

                    yield data

                yield "__DONE__"

            except ValueError as e:

                print(
                    "========== STREAM VALUE ERROR =========="
                )

                print(str(e))

                yield json.dumps({
                    "error": "DOC_NOT_FOUND"
                })

            except Exception as e:

                print(
                    "========== STREAM QUERY ERROR =========="
                )

                print(
                    f"Error type: {type(e).__name__}"
                )

                print(
                    f"Error message: {str(e)}"
                )

                traceback.print_exc()

                yield json.dumps({
                    "error": "LLM_ERROR"
                })

        return StreamingResponse(
            event_generator(),
            media_type="text/plain"
        )

    except ValueError as e:

        if "Collection" in str(e):

            raise HTTPException(
                status_code=404,
                detail="DOC_NOT_FOUND"
            )

        raise HTTPException(
            status_code=500,
            detail="PROCESSING_ERROR"
        )

    except Exception as e:

        print("========== STREAM SETUP ERROR ==========")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")

        traceback.print_exc()

        raise HTTPException(
            status_code=503,
            detail="LLM_UNAVAILABLE"
        )


# ============================================================
# GET SESSION HISTORY
# ============================================================

@app.get(
    "/sessions/{doc_id}",
    response_model=SessionHistory
)
async def get_session(doc_id: str):

    print(
        f"========== GET SESSION: {doc_id} =========="
    )

    engine = get_rag_engine()

    if engine is None:

        raise HTTPException(
            status_code=503,
            detail="RAG_DEPENDENCIES_MISSING"
        )

    try:

        history = engine.get_session_history(
            doc_id
        )

        return SessionHistory(
            history=history
        )

    except Exception as e:

        print("========== SESSION ERROR ==========")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="SESSION_ERROR"
        )


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.delete("/document/{doc_id}")
async def delete_document(doc_id: str):

    print(
        f"========== DELETE DOCUMENT: {doc_id} =========="
    )

    engine = get_rag_engine()

    if engine is None:

        raise HTTPException(
            status_code=503,
            detail="RAG_DEPENDENCIES_MISSING"
        )

    try:

        result = engine.delete_document(
            doc_id
        )

        return result

    except Exception as e:

        print("========== DELETE DOCUMENT ERROR ==========")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")

        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="DELETE_ERROR"
        )


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )