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

# Verify database file was copied
RUN ls -lh hydropage.db && echo "Database found!" && \
    python -c "import sqlite3; conn = sqlite3.connect('hydropage.db'); print(f'Tables: {[r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\"\").fetchall()]}'); conn.close()"

# Set default PORT if not provided (Railway will override)
ENV PORT=8080

# Expose port
EXPOSE 8080

# Start command - verify database exists, then start gunicorn with logging
CMD /bin/sh -c "echo 'Starting Hydropage API...' && \
    ls -lh hydropage.db && \
    echo 'Starting gunicorn on port ${PORT}...' && \
    gunicorn app:app \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --timeout 120 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    --preload"
