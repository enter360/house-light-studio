ARG BUILD_FROM=ghcr.io/hassio-addons/base:latest
FROM $BUILD_FROM

# Install Python 3 + pip
RUN apk add --no-cache python3 py3-pip

# Copy app source
WORKDIR /app
COPY src/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY src/ .

# Copy the designer UI so we can serve it through ingress
COPY ../index.html ./static/index.html

# Persistent data directory (sequences, device registry)
VOLUME ["/data"]

CMD ["python3", "-u", "main.py"]
