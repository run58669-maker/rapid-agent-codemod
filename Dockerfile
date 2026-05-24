# Cloud Run image for the Migration Agent.
# Layers: Python base → Node (for jssg codemod runner) → app deps → app code.
FROM python:3.12-slim

# Node 20+ (codemod jssg needs it) + git
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt flask gunicorn

# App code (agent + tools + codemod sibling + server)
COPY agent ./agent
COPY tools ./tools
COPY server ./server
COPY README.md ./

# Sibling codemod repo — copied as ../codemod-web3py-v7 to match the
# CODEMOD_REGISTRY path in tools/run_codemod.py.
COPY codemod-web3py-v7 /codemod-web3py-v7
RUN ln -s /codemod-web3py-v7 /app/../codemod-web3py-v7 || true

# Pre-warm npx cache for the codemod CLI (saves cold-start latency)
RUN cd /tmp && npx --yes codemod --version || true

# GitLab MCP OAuth tokens (baked from local mcp-remote cache at build time)
COPY .mcp-auth /root/.mcp-auth

# Configure git identity for committed-MR runs
RUN git config --global user.name "Migration Agent" \
    && git config --global user.email "agent@migration-agent.local"

ENV PORT=8080
EXPOSE 8080

# gunicorn for production. Single worker, long timeout — agent runs take 30-60s.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "300", "server.app:app"]
