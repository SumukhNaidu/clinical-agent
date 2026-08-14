import os
import shutil
import json
import traceback
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from models import UploadResponse, QueryRequest, QueryResponse, SessionHistory


load_dotenv()

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    force=True
)

logger = logging.getLogger("cliniq")


# ============================================================
# APP
# ============================================================

app = FastAPI(title="ClinIQ API")

rag_engine = None


# ============================================================
# DEBUG VERSION
# ============================================================

@app.get("/debug")
async def debug():
    logger.info("DEBUG ENDPOINT WAS CALLED")

    return {
        "status": "ok",
        "version": "UPLOAD_DEBUG_V2",
        "message": "This is the new deployed api.py"
    }


# ============================================================
# RAG ENGINE
# ============================================================

def get_rag_engine():
    global rag_engine

    if rag_engine is None:
        try:
            logger.info("========== INITIALIZING RAG ENGINE ==========")

            from rag_engine import RAGEngine

            rag_engine = RAGEngine()

            logger.info("========== RAG ENGINE INITIALIZED ==========")

        except Exception as e:
            logger.error("========== RAG ENGINE INITIALIZATION ERROR ==========")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.error(traceback.format_exc())

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
# TEMP DIRECTORY
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
        "health": "/health",
        "debug": "/debug"
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health_check():
    logger.info("HEALTH ENDPOINT CALLED")

    return {
        "status": "ok"
    }


# ============================================================
# UPLOAD
# ============================================================

@app.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    domain: str = Form("general")
):

    # THIS MUST APPEAR IN RENDER LOGS
    logger.info("================================================")
    logger.info("========== POST /upload RECEIVED ===============")
    logger.info(f"Filename: {file.filename}")
    logger.info(f"Domain: {domain}")
    logger.info("================================================")

    # --------------------------------------------------------
    # Validate filename
    # --------------------------------------------------------

    if not file.filename:
        logger.error("No filename received")

        raise HTTPException(
            status_code=400,
            detail="INVALID_FILE_NAME"
        )

    filename = os.path.basename(file.filename)
    filename_lower = filename.lower()

    logger.info(f"Safe filename: {filename}")

    # --------------------------------------------------------
    # Validate file type
    # --------------------------------------------------------

    if not (
        filename_lower.endswith(".pdf")
        or filename_lower.endswith(".docx")
    ):

        logger.error(
            f"Invalid file type: {filename}"
        )

        raise HTTPException(
            status_code=400,
            detail="INVALID_FILE_TYPE"
        )

    # --------------------------------------------------------
    # File size
    # --------------------------------------------------------

    try:

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        logger.info(
            f"File size: {file_size} bytes"
        )

    except Exception as e:

        logger.error(
            f"FILE SIZE ERROR: {str(e)}"
        )

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
    # Save file
    # --------------------------------------------------------

    temp_path = os.path.join(
        "./temp_uploads",
        filename
    )

    logger.info(
        f"Saving uploaded file to: {temp_path}"
    )

    try:

        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer
            )

        logger.info("FILE SAVED SUCCESSFULLY")

    except Exception as e:

        logger.error("========== FILE SAVE ERROR ==========")
        logger.error(
            f"Error type: {type(e).__name__}"
        )
        logger.error(
            f"Error message: {str(e)}"
        )
        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(
            status_code=500,
            detail="FILE_SAVE_ERROR"
        )

    # --------------------------------------------------------
    # RAG ENGINE
    # --------------------------------------------------------

    logger.info("Getting RAG engine...")

    engine = get_rag_engine()

    if engine is None:

        logger.error(
            "RAG ENGINE IS NONE"
        )

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
    # PROCESS DOCUMENT
    # --------------------------------------------------------

    try:

        logger.info(
            "========== STARTING RAG PROCESSING =========="
        )

        logger.info(
            f"Calling engine.process_document()"
        )

        result = engine.process_document(
            temp_path,
            filename,
            domain=domain
        )

        logger.info(
            "========== RAG PROCESSING SUCCESS =========="
        )

        logger.info(
            f"Result: {result}"
        )

        return UploadResponse(**result)

    except Exception as e:

        logger.error(
            "================================================"
        )

        logger.error(
            "========== RAG PROCESSING ERROR ================"
        )

        logger.error(
            f"Error type: {type(e).__name__}"
        )

        logger.error(
            f"Error message: {str(e)}"
        )

        logger.error(
            "========== FULL TRACEBACK ======================"
        )

        logger.error(
            traceback.format_exc()
        )

        logger.error(
            "================================================"
        )

        # TEMPORARILY expose actual error
        raise HTTPException(
            status_code=500,
            detail=(
                f"PROCESSING_ERROR: "
                f"{type(e).__name__}: "
                f"{str(e)}"
            )
        )

    finally:

        if os.path.exists(temp_path):

            try:

                os.remove(temp_path)

                logger.info(
                    "Temporary file deleted."
                )

            except Exception as e:

                logger.warning(
                    f"Could not delete temp file: {str(e)}"
                )


# ============================================================
# QUERY
# ============================================================

@app.post("/query", response_model=QueryResponse)
async def query_document(request: QueryRequest):

    logger.info("========== POST /query RECEIVED ==========")

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

        logger.error(
            f"QUERY VALUE ERROR: {str(e)}"
        )

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

        logger.error(
            f"QUERY ERROR: {str(e)}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(
            status_code=503,
            detail="LLM_UNAVAILABLE"
        )


# ============================================================
# STREAM QUERY
# ============================================================

@app.post("/query/stream")
async def query_document_stream(
    request: QueryRequest
):

    logger.info(
        "========== POST /query/stream RECEIVED =========="
    )

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

            except Exception as e:

                logger.error(
                    f"STREAM ERROR: {str(e)}"
                )

                logger.error(
                    traceback.format_exc()
                )

                yield json.dumps({
                    "error": "LLM_ERROR"
                })

        return StreamingResponse(
            event_generator(),
            media_type="text/plain"
        )

    except Exception as e:

        logger.error(
            f"STREAM SETUP ERROR: {str(e)}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(
            status_code=503,
            detail="LLM_UNAVAILABLE"
        )


# ============================================================
# SESSION
# ============================================================

@app.get(
    "/sessions/{doc_id}",
    response_model=SessionHistory
)
async def get_session(doc_id: str):

    logger.info(
        f"GET SESSION: {doc_id}"
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

        logger.error(
            f"SESSION ERROR: {str(e)}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(
            status_code=500,
            detail="SESSION_ERROR"
        )


# ============================================================
# DELETE DOCUMENT
# ============================================================

@app.delete("/document/{doc_id}")
async def delete_document(doc_id: str):

    logger.info(
        f"DELETE DOCUMENT: {doc_id}"
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

        logger.error(
            f"DELETE ERROR: {str(e)}"
        )

        logger.error(
            traceback.format_exc()
        )

        raise HTTPException(
            status_code=500,
            detail="DELETE_ERROR"
        )


# ============================================================
# LOCAL
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            8000
        )
    )

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )