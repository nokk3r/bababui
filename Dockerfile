FROM python:3.12-slim-bookworm AS bins

ARG TARGETARCH
ARG XRAY_VERSION=26.10.29
ARG HYSTERIA_VERSION=2.13.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) XARCH=64; HARCH=amd64 ;; \
      arm64) XARCH=arm64-v8a; HARCH=arm64 ;; \
      *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 3 -o /tmp/xray.zip \
      "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-${XARCH}.zip"; \
    unzip /tmp/xray.zip -d /tmp/xray; \
    install -m 755 /tmp/xray/xray /usr/local/bin/xray; \
    curl -fsSL --retry 3 -o /usr/local/bin/hysteria \
      "https://github.com/apernet/hysteria/releases/download/app/v${HYSTERIA_VERSION}/hysteria-linux-${HARCH}"; \
    chmod 755 /usr/local/bin/hysteria; \
    xray version; \
    hysteria version; \
    hysteria client --help >/dev/null

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 checker \
    && command -v runuser >/dev/null

COPY --from=bins /usr/local/bin/xray /usr/local/bin/xray
COPY --from=bins /usr/local/bin/hysteria /usr/local/bin/hysteria

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /data \
    && chown checker:checker /data

ENV DATA_DIR=/data \
    XRAY_BIN=/usr/local/bin/xray \
    HYSTERIA_BIN=/usr/local/bin/hysteria \
    CURL_BIN=/usr/bin/curl \
    PYTHONUNBUFFERED=1

EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
