
from pydantic import BaseModel
from typing import List, Optional


class UploadResponse(BaseModel):
    status: str
    doc_id: str
    filename: str
    chunk_count: int


class Citation(BaseModel):
    chunk_id: str
    page: Optional[int] = None
    section: Optional[str] = None
    content: str


class QueryRequest(BaseModel):
    doc_id: str
    question: str
    domain: Optional[str] = 'general'


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    latency_ms: float


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    citations: Optional[List[Citation]] = None


class SessionHistory(BaseModel):
    history: List[ChatMessage]
