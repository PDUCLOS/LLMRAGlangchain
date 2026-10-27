# ===========================================================================
# erp-ai-copilot — image de l'API (et des Jobs : ingestion, banc LLMOps)
#
#   docker build -t erp-ai-copilot:0.2.0 .
#   docker run -p 8000:8000 --env-file .env erp-ai-copilot:0.2.0
#
# Une seule image pour l'API, le Job d'ingestion et le CronJob LLMOps :
# seule la commande change. Le LLM n'est PAS dans l'image (il est servi par
# Ollama ou Azure OpenAI) : l'image reste petite et sans GPU.
# ===========================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data

# Pilote ODBC Microsoft 18 : nécessaire pour SQL Server (pyodbc).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get purge -y gnupg && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances d'abord : la couche reste en cache tant que pyproject ne change pas.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install -e ".[sqlserver,ollama]"

COPY eval ./eval
COPY scripts ./scripts
COPY sql ./sql

# Utilisateur non root (exigé par la plupart des politiques Kubernetes).
RUN useradd --uid 10001 --create-home app && mkdir -p /app/data && chown -R app /app/data
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "erp_ai.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
