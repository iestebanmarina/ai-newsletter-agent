# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install build deps for lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt-dev && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy source and install project
COPY src/ src/
RUN uv sync --frozen

# Stage 2: Runtime
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Runtime deps for lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends libxml2 libxslt1.1 && \
    rm -rf /var/lib/apt/lists/*

# Copy virtual environment and source from builder
COPY --from=builder /app /app

VOLUME /data

ENV TZ=UTC

CMD ["uv", "run", "newsletter", "--schedule"]
