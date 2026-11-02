FROM python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

ARG SCOPE_RECALL_VERSION
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m pip install --no-cache-dir --only-binary=:all: "hermes-scope-recall[lancedb,codex]==${SCOPE_RECALL_VERSION}"
WORKDIR /app
COPY --chmod=644 worker-loop.py /app/worker-loop.py
USER 1000:1001
CMD ["scope-recall", "--help"]
