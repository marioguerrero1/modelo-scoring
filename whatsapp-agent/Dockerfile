FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY business.yaml .
ENV DATABASE_PATH=/data/agent.db
VOLUME /data
EXPOSE 8000
# Los hostings tipo Railway/Render indican el puerto en la variable PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
