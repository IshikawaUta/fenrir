# Fenrir — hybrid Python web framework runtime image.
#
# asteri (the ASGI server Fenrir uses) is only distributed as an sdist and
# ships a C extension, so wheels are built in a builder stage (with gcc) and
# installed into a slim runtime image that stays free of build tools.
#
# The image includes the full Fenrir framework (Redis sessions, aiosqlite/
# asyncpg ORM, Strawberry GraphQL and gRPC) plus a small example app so it is
# runnable out of the box. Mount your own app at /app and override APP_MODULE
# (format "module:app") to serve it instead.

FROM python:3.13-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Install Fenrir first so dependency layers are cached independently of app code.
COPY pyproject.toml README.md ./
COPY fenrir/ fenrir/
RUN python -m pip install --upgrade pip \
    && python -m pip wheel --no-cache-dir -w /wheels ".[all]"

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Bundled example application.
COPY demo_app.py demo_app.py
COPY templates/ templates/
COPY logo.png logo.png
COPY logo.jpg logo.jpg
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint
RUN chmod +x /usr/local/bin/docker-entrypoint

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint"]