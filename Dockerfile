FROM python:3.13-slim

# Install git and uv
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy entrypoint that configures git auth at runtime
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

# Copy application files
COPY server.py git_archaeology.py generate_repos_list.py repos_config.json ./
COPY index.html ./
COPY js/ js/
COPY css/ css/
COPY charts/ charts/

# Pre-install script dependencies so first regeneration is faster
RUN uv run --with marimo --with "polars==1.35.2" --with "altair==6.0.0" \
    --with "pydantic>=2.0.0" --with "diskcache==5.6.3" --with "tenacity>=8.0.0" \
    --with "httpx>=0.27.0" python -c "print('deps cached')"

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uv", "run", "server.py", "0.0.0.0", "8000"]
