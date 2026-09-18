# Fallback build. Railway uses Railpack via railway.json; this is here so the app
# runs the same way anywhere else (Fly, Render, a VPS): docker build . && docker run -p 8000:8000 ...
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY packs ./packs
COPY db ./db
ENV PATH="/srv/.venv/bin:$PATH" PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --no-access-log --proxy-headers --forwarded-allow-ips='*'"]
