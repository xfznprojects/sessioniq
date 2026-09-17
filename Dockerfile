FROM node:24-alpine AS dashboard

WORKDIR /build

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable

COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY web ./
RUN pnpm build


FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SESSIONIQ_HOST=0.0.0.0 \
    SESSIONIQ_STATIC_DIR=/app/web/dist

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY scripts ./scripts
COPY --from=dashboard /build/dist ./web/dist

# Generate the demo library into the image. Audio analysis is the expensive
# part of this app and librosa is imported lazily, so doing it here means a
# cold start serves a populated dashboard in seconds instead of analyzing
# thirteen files on the first request.
RUN python scripts/seed_demo.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('SESSIONIQ_PORT') or os.environ.get('PORT') or '8000'; urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3)"

CMD ["python", "scripts/docker_entrypoint.py"]
