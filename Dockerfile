# Use official Python 3.10 slim image
FROM python:3.10-slim-bullseye

# Set working directory
WORKDIR /app


# Install system dependencies
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y libpq-dev gcc

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure app directory is recognized as a package
RUN touch app/__init__.py

# Create non-root user and set permissions
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose Streamlit port
EXPOSE 8501

# Healthcheck for Render
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default command to run Streamlit dashboard
CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]

