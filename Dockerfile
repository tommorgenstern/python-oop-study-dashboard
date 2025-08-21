FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure .env exists (copy default if missing)
RUN if [ ! -f .env ] && [ -f .env.example ]; then cp .env.example .env; fi

RUN useradd -m appuser
USER appuser

ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--workers", "2"]
