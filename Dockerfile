# deco-local: web UI + REST API for strictly-local TP-Link Deco control (no cloud).
# The GTK desktop app needs a display and ships as an AppImage instead (packaging/).
FROM python:3.12-slim

ARG VERSION=dev
# Links the image to its repository on GitHub Container Registry and describes it there.
LABEL org.opencontainers.image.source="https://github.com/averagenative/deco-local" \
      org.opencontainers.image.title="deco-local" \
      org.opencontainers.image.description="Manage a TP-Link Deco mesh locally: web UI and REST API, no TP-Link cloud." \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}"

WORKDIR /app

COPY requirements-rest.txt ./
RUN pip install --no-cache-dir -r requirements-rest.txt

# The API, the backend modules, the opcode map deco_api loads at import, and the web UI.
COPY deco_rest.py deco_api.py deco_demo.py deco_features.py deco_log.py deco-opcodes.json ./
COPY web ./web

# Credentials: $TPLINK_USER + $TPLINK_PASS (env file), or a two-line file at
# $DECO_CREDS_PATH that this user can read.
# DECO_API_HOST=127.0.0.1 binds loopback only; set 0.0.0.0 (or a bridge IP) to expose it.
ENV DECO_API_HOST=127.0.0.1 \
    DECO_API_PORT=8777 \
    DECO_ALLOWED_HOSTS=* \
    DECO_IDLE_SECONDS=300 \
    DECO_CREDS_PATH=/creds/.tplink_cloud \
    DECO_LOG_LEVEL=INFO \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
EXPOSE 8777

HEALTHCHECK --interval=30s --timeout=6s --start-period=10s --retries=3 \
    CMD ["python", "deco_rest.py", "--healthcheck"]

CMD ["python", "deco_rest.py"]
