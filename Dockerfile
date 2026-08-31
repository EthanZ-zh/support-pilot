FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv==0.12.7
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY data ./data
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 supportpilot && chown -R supportpilot:supportpilot /app
USER supportpilot

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "support_pilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
