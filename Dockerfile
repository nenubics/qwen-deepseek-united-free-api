FROM python:3.11-slim

# System dependencies for Chromium, Playwright, and xvfb virtual display
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    curl \
    xvfb \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and its OS dependencies
RUN playwright install --with-deps chromium

# Copy app code, CLI, and static assets
COPY app ./app
COPY login.py .
COPY .env.example .

# Create persistent storage directories
RUN mkdir -p /app/data /app/session /app/logs

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

# xvfb-run allows both headless and headed browser contexts inside container
CMD ["xvfb-run", "-a", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
