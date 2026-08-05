# Image base: python slim + Node 20 (required for baileys per-number workers)
FROM python:3.11-slim

# Install Node.js 20 + git + build tools (needed by some native deps like sharp)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project
COPY . .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Install Node deps (Baileys engine + companion server)
RUN npm install --omit=dev --legacy-peer-deps --no-audit --no-fund

# Default command: launch the master orchestrator (index.py)
CMD ["python", "index.py"]
