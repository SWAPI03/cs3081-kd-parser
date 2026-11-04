# Inference service image (Task 3): CPU-only, every version pinned, NO model weights inside.
# The weights are downloaded from object storage when the container starts.
# Build from the repository root:  docker build -f service/Dockerfile -t kd-parser:v1 .
FROM python:3.11.10-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    SCHEMA_PATH=/app/schema.json OMP_NUM_THREADS=1
WORKDIR /app

# The default torch wheel bundles CUDA libraries (several GB). The CPU wheel is about 200 MB.
RUN pip install torch==2.4.1+cpu --index-url https://download.pytorch.org/whl/cpu
COPY service/requirements.txt .
RUN pip install -r requirements.txt

COPY data/schema.json /app/schema.json
COPY service/inference.py service/app.py /app/

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "20"]
