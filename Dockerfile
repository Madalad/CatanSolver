# Container image for the CatanSolver web app — portable across any host that runs
# Docker (Render, Fly, HF Spaces, a VPS, a GPU box). Build: `docker build -t catansolver .`
# Run locally: `docker run -p 8000:8000 -e PORT=8000 catansolver`
FROM python:3.11-slim

WORKDIR /app

# Install deps first so they cache across code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + committed model artifacts (docs/*.json are loaded at runtime).
COPY catansolver/ ./catansolver/
COPY docs/ ./docs/

# Hosts inject the port via $PORT; default to 8000 for local runs.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn catansolver.api.app:app --host 0.0.0.0 --port ${PORT}"]
