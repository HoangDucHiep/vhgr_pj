FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt backend/requirements.txt ./
# `torch` bản CPU: extra index chính thức PyTorch (image slim, không CUDA).
# `--extra-index-url` chỉ **thêm** index — PyPI vẫn được ưu tiên cho package
# không có trên index torch (tránh kéo bản CUDA mặc định).
RUN pip install --upgrade pip \
    && pip install --extra-index-url https://download.pytorch.org/whl/cpu \
        "torch>=2.4" \
    && pip install -r requirements.txt

COPY src/ ./src/
COPY backend/ ./backend/
COPY configs/ ./configs/
COPY scripts/ ./scripts/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
