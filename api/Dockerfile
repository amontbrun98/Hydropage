# Use Python 3.9 slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set default PORT if not provided (Railway will override)
ENV PORT=8080

# Expose port
EXPOSE 8080

# Start command - use shell to expand environment variables
CMD /bin/sh -c "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --timeout 120"
