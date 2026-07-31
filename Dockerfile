FROM node:24-alpine AS web-builder
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim AS python-builder
WORKDIR /build
COPY pyproject.toml ./
COPY src/ src/
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.11-slim AS runtime
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 harness \
    && useradd --system --uid 10001 --gid harness --home-dir /app harness
WORKDIR /app
COPY --from=python-builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels coding-agent-harness==0.1.0 \
    && rm -rf /wheels
COPY src/ src/
COPY scripts/ scripts/
COPY --from=web-builder /build/web/dist web/dist/
RUN mkdir -p /state /workspace && chown -R harness:harness /app /state /workspace

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HARNESS_LLM_PROVIDER=mock
VOLUME ["/state"]
EXPOSE 8000
USER harness
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2).read(1)"
CMD ["python", "scripts/serve_demo.py", "--ready-file", "/state/ready.json", "--runtime-root", "/state", "--host", "0.0.0.0", "--port", "8000", "--project-source", "/workspace/project", "--max-seconds", "86400"]
