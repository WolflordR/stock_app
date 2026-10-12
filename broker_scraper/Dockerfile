FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
RUN python -c "import ddddocr; ddddocr.DdddOcr(show_ad=False)"
COPY . /app/broker_scraper

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=Asia/Taipei

CMD ["python", "-m", "broker_scraper.scheduler"]
