FROM python:3.12-slim
WORKDIR /opt/jrc-manager
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV JRC_PUBLIC_HOST_MODE=1
ENV JRC_CLOUD_PRIMARY_MODE=1
ENV JRC_SESSION_TIMEOUT_MINUTES=120
ENV JRC_DATA_DIR=/var/data/jrc
COPY . .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
EXPOSE 8765
CMD sh -c 'mkdir -p ${JRC_DATA_DIR:-/var/data/jrc} && gunicorn cloud_hosting.cloud_entry:app --workers ${JRC_GUNICORN_WORKERS:-2} --threads ${JRC_GUNICORN_THREADS:-4} --timeout ${JRC_GUNICORN_TIMEOUT:-120} --bind 0.0.0.0:${PORT:-8765}'
