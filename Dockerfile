FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build
RUN pip install --no-cache-dir --upgrade pip build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/autopeer/.local/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ansible-core \
       bird2 \
       git \
       openssh-client \
       rsync \
       wireguard-tools \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin autopeer \
    && mkdir -p /data/autopeer /config-repo \
    && chown autopeer:autopeer /data/autopeer

WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl
COPY --chown=autopeer:autopeer config ./config

USER autopeer
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).read()"

CMD ["uvicorn", "autopeer.main:app", "--host", "0.0.0.0", "--port", "8080"]
