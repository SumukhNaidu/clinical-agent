FROM python:3.11-slim
WORKDIR /app

# system deps (adjust if you use packages needing build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1
ENV CHROMA_PERSIST_DIR=/data/chroma_data
EXPOSE 8005

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8005"]
