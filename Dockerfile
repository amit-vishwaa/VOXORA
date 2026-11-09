# UNTESTED template for cloud deployment. SQLite is single-node: move to PostgreSQL before scaling (see docs).
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
ENV HOST=0.0.0.0 PORT=8080 VOXORA_INSTANCE_DIR=/data
VOLUME /data
EXPOSE 8080
WORKDIR /app/backend
CMD ["python", "manage.py", "run"]
