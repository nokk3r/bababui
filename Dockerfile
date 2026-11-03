FROM python:3.12-slim-bookworm AS bins

ARG TARGETARCH
ARG XRAY_VERSION=26.10.31
ARG HYSTERIA_VERSION=2.13.0
ARG SPEEDTEST_VERSION=1.8.3
ARG XRAY_SHA256_AMD64=e4bd9119f50ae7c41658b1abd0679ae06f98bd864a2907ff33f2f2cf7081b214
ARG XRAY_SHA256_ARM64=1811c8f1da0c3b6dc707ebaf1c8390e987ba39859a8f0a7aadd8526157f2ec8d
ARG HYSTERIA_SHA256_AMD64=907ba8c9693edb104b20582681fb7dc15639d5b64a9cbb616a7b539190a86691
ARG HYSTERIA_SHA256_ARM64=a68a61a84452ca250ce0368202521965ca9cc9d801a404f1dc9008ac6cf677a7
ARG SPEEDTEST_SHA256_AMD64=c55caae22927cd719a2f8c0bef96ecf74b5fe8ca919ff9200d76328ae5de9477
ARG SPEEDTEST_SHA256_ARM64=48f51504548d76d5dc2ce7f72e713bd3b4e35554028b7131467060688754c657

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$TARGETARCH" in \
      amd64) \
        XARCH=64; HARCH=amd64; STARCH=x86_64; \
        XSHA="$XRAY_SHA256_AMD64"; HSHA="$HYSTERIA_SHA256_AMD64"; STSHA="$SPEEDTEST_SHA256_AMD64" ;; \
      arm64) \
        XARCH=arm64-v8a; HARCH=arm64; STARCH=arm64; \
        XSHA="$XRAY_SHA256_ARM64"; HSHA="$HYSTERIA_SHA256_ARM64"; STSHA="$SPEEDTEST_SHA256_ARM64" ;; \
      *) echo "unsupported arch: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 3 -o /tmp/xray.zip \
      "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-${XARCH}.zip"; \
    echo "$XSHA  /tmp/xray.zip" | sha256sum -c -; \
    unzip /tmp/xray.zip -d /tmp/xray; \
    install -m 755 /tmp/xray/xray /usr/local/bin/xray; \
    curl -fsSL --retry 3 -o /tmp/hysteria \
      "https://github.com/apernet/hysteria/releases/download/app/v${HYSTERIA_VERSION}/hysteria-linux-${HARCH}"; \
    echo "$HSHA  /tmp/hysteria" | sha256sum -c -; \
    install -m 755 /tmp/hysteria /usr/local/bin/hysteria; \
    curl -fsSL --retry 3 -o /tmp/speedtest.tgz \
      "https://github.com/showwin/speedtest-go/releases/download/v${SPEEDTEST_VERSION}/speedtest-go_${SPEEDTEST_VERSION}_Linux_${STARCH}.tar.gz"; \
    echo "$STSHA  /tmp/speedtest.tgz" | sha256sum -c -; \
    tar -xzf /tmp/speedtest.tgz -C /tmp speedtest-go; \
    install -m 755 /tmp/speedtest-go /usr/local/bin/speedtest-go; \
    xray version; \
    hysteria version; \
    hysteria client --help >/dev/null; \
    speedtest-go --version

FROM --platform=$BUILDPLATFORM node:24-slim AS web

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
COPY static ../static
RUN npm run build

FROM python:3.12-slim-bookworm

# MIT покрывает само приложение. В образе рядом лежат Xray (MPL-2.0),
# Hysteria и speedtest-go (MIT) и шрифт Inter (OFL-1.1); тексты в third_party/.
LABEL org.opencontainers.image.source="https://github.com/nokk3r/bababui" \
      org.opencontainers.image.licenses="MIT AND MPL-2.0 AND OFL-1.1" \
      org.opencontainers.image.description="Local speed test for subscription nodes with a web interface"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /usr/local/share/licenses/bababui \
    && useradd --create-home --uid 10001 checker \
    && command -v runuser >/dev/null

COPY --from=bins /usr/local/bin/xray /usr/local/bin/xray
COPY --from=bins /usr/local/bin/hysteria /usr/local/bin/hysteria
COPY --from=bins /usr/local/bin/speedtest-go /usr/local/bin/speedtest-go
COPY third_party/ /usr/local/share/licenses/
COPY LICENSE /usr/local/share/licenses/bababui/LICENSE

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY --from=web /src/frontend/dist ./static
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh \
    && chmod -R a+rX /app/static /usr/local/share/licenses \
    && mkdir -p /data \
    && chown checker:checker /data

ENV DATA_DIR=/data \
    XRAY_BIN=/usr/local/bin/xray \
    HYSTERIA_BIN=/usr/local/bin/hysteria \
    SPEEDTEST_BIN=/usr/local/bin/speedtest-go \
    PYTHONUNBUFFERED=1

EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/health || exit 1
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
