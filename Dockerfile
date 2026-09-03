FROM python:3.9-slim

WORKDIR /app

# Gerekli paketleri yukle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulamayi kopyala
COPY flask_transcript_api.py .

# 5000 portunu disari ac
EXPOSE 5000

# Uygulamayi baslat
CMD ["python", "flask_transcript_api.py"]
