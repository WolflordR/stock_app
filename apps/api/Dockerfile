FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps ./apps
COPY modules ./modules
COPY packages ./packages
COPY migrations ./migrations
COPY services ./services

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
