# Contask NF: imagem de uma instância (um escritório por contêiner).
# Build: docker build -t contask-nf .

# 1) Interface
FROM node:24-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) Servidor
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTASK_HOST=0.0.0.0 \
    CONTASK_PORTA=8765 \
    CONTASK_LOGIN=true \
    CONTASK_COOKIE_SEGURO=true \
    CONTASK_DADOS_DIR=/app/dados \
    CONTASK_FRONTEND_DIST=/app/frontend/dist \
    CONTASK_CHAVE_MESTRA_ARQUIVO=/segredos/chave.key \
    TZ=America/Sao_Paulo

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=frontend /src/frontend/dist frontend/dist

# Usuário sem privilégios; as pastas montadas devem pertencer ao UID 1000
RUN useradd --uid 1000 --create-home contask \
    && mkdir -p /app/dados /segredos /backups \
    && chown -R contask:contask /app/dados /segredos /backups
USER contask

EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/ping', timeout=4)"

# Só o Caddy (mesma rede Docker) acessa a porta; ele informa o IP real do cliente.
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8765", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
