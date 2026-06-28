FROM python:3.11-slim AS base

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip cache purge

COPY .streamlit/ .streamlit/
COPY memorylane/ memorylane/
COPY app.py .

USER appuser

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
