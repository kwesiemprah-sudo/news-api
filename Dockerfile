# Start from a small official Python image
FROM python:3.12-slim

# Don't write .pyc files; send output straight to the log (no buffering)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# All following commands run inside this directory in the container
WORKDIR /app

# Copy dependency list first, so Docker can cache this layer
COPY requirements.txt .

# Install dependencies; --no-cache-dir keeps the image small
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the application source
COPY src/ ./src/

# Create and switch to a non-root user for security
RUN useradd --create-home appuser
USER appuser

# Document which port the container listens on
EXPOSE 8080

# Start the server, bound to 0.0.0.0 so it accepts external connections
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]