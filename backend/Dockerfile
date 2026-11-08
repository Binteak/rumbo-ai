FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Usuario sin privilegios con UID numérico (lo exige runAsNonRoot en Kubernetes).
RUN useradd --uid 10001 --create-home rumbo && mkdir -p /data && chown 10001 /data
USER 10001

ENV DATABASE_URL=sqlite:////data/rumbo.db
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
