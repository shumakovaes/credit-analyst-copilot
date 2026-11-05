FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 LANGSMITH_TRACING=false
COPY requirements.lock .
RUN pip install -r requirements.lock
COPY . .
RUN pip install --no-deps .
CMD ["uvicorn", "credit_copilot.api:app", "--host", "0.0.0.0", "--port", "8001"]
