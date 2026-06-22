FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV JRC_PORT=8765
ENV JRC_PUBLIC_HOST_MODE=1
ENV JRC_SESSION_TIMEOUT_MINUTES=60
EXPOSE 8765
CMD ["python", "-m", "app.network_server"]
