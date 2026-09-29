FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -m app
COPY app/ .
USER app
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]
