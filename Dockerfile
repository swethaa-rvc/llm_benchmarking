FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# .env, models.json, pricing.json, sla_targets.json and benchmark.db are
# secrets/runtime data - not baked into the image (see .dockerignore).
# Mount them at `docker run` time, e.g.:
#   docker run -p 8000:8000 --env-file .env \
#     -v %cd%/models.json:/app/models.json \
#     -v %cd%/benchmark.db:/app/benchmark.db \
#     llm-ops-benchmark
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8000"]
