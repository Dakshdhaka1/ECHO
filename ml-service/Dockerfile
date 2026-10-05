# ECHO ML service (FastAPI). Python 3.12 pinned for ML wheel compatibility (ARCHITECTURE §5).
# INSTALL_TRAINING=true also installs the training stack (MLflow, Optuna, CPU PyTorch, Transformers) so the
# admin "retrain" button and the scheduled retraining work inside the container. Set it to false for a slim
# inference-only image.
FROM python:3.12-slim

ARG INSTALL_TRAINING=true
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MODEL_DIR=/app/artifacts ECHO_DATA_DIR=/data DATA_DIR=/data MLFLOW_DISABLE_AGENT_HINT=1

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-train.txt ./
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_TRAINING" = "true" ]; then \
         pip install torch --index-url https://download.pytorch.org/whl/cpu && \
         pip install -r requirements-train.txt ; \
       fi

COPY app ./app
COPY pipelines ./pipelines
COPY mappings ./mappings
COPY configs ./configs
COPY pyproject.toml ./

RUN useradd --create-home --uid 10001 echo && mkdir -p /app/artifacts /app/mlruns /app/reports && chown -R echo /app
USER echo

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 CMD curl -fs http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
