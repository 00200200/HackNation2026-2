# Extraction API for doc2json.pl (kio2json.web_api). Installs exactly what the jury installs: requirements.txt.
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
COPY packaging ./packaging
RUN pip install --no-cache-dir -r requirements.txt
COPY kio2json ./kio2json
COPY config ./config
COPY frontend/public ./frontend/public
RUN useradd --system --uid 10001 app
USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "kio2json.web_api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
