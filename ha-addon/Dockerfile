ARG BUILD_FROM=ghcr.io/hassio-addons/base:latest
FROM $BUILD_FROM

# Install Python 3 + pip
RUN apk add --no-cache python3 py3-pip

# Copy app source
WORKDIR /app
COPY src/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt --break-system-packages

COPY src/ .

# The designer UI is copied here by the build script (build.sh) before
# `docker build` runs, because Docker cannot reach outside its build context.
# See build.sh for details.
COPY static/ ./static/

# Persistent data directory (sequences, device registry)
VOLUME ["/data"]

CMD ["python3", "-u", "main.py"]
