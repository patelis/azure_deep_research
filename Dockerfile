# Single image: the py-shiny app importing the backend in-process. uv-managed throughout.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Copy the whole uv workspace (root lock + both members) and install from the frozen lockfile
# for a reproducible build. Workspace members are installed editable, so sources must be present.
COPY pyproject.toml uv.lock .python-version ./
COPY backend/ backend/
COPY frontend/ frontend/
COPY utils/ utils/

RUN uv sync --all-packages --frozen --no-dev

EXPOSE 8000
# Container Apps ingress targetPort = 8000. Shiny serves the chat UI; it imports `deep_research`.
CMD ["uv", "run", "shiny", "run", "frontend/app.py", "--host", "0.0.0.0", "--port", "8000"]
