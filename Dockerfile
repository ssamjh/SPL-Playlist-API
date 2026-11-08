FROM python:3.14-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

ENV PATH="/app/.venv/bin:$PATH"

COPY server.py .

VOLUME ["/playlists"]

EXPOSE 5000

ENV PLAYLIST_DIR=/playlists

CMD ["python", "server.py"]
