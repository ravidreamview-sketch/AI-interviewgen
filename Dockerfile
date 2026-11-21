# Python 3.12 slim image for linux/amd64
FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

# Prevent Python from writing .pyc files & enable unbuffered stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Expose default port (Cloud Run will inject $PORT)
ENV PORT=8080
EXPOSE 8080

# Run Uvicorn server dynamically binding to $PORT
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
