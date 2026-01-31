FROM python:3.12-slim

# Install libpq-dev for Postgres compatibility
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Copy requirements from root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app folder
COPY ./app ./app

# Run from the root so "app.main:app" import works
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]