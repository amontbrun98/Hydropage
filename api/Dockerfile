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
    python -c "import sqlite3; conn = sqlite3.connect('hydropage.db'); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=\"table\"'); print('Tables found:', cur.fetchone()[0]); conn.close()"

# Set default PORT if not provided (Railway will override)
ENV PORT=8080

# Expose port
EXPOSE 8080

# Add healthcheck directly in Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\", \"8080\")}/api/health').read()" || exit 1

# Start command - simplified for Railway
CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --worker-class sync \
    --timeout 120 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance
