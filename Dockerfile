FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
# The two MCP servers live in the same image so the extractor can spawn them over stdio.
RUN pip install --no-cache-dir -r requirements.txt analytics-mcp meta-ads-mcp

COPY . .
ENV DB_PATH=/app/data/marketing.db
