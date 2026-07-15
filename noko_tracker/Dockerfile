FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN VITE_API_BASE_URL=./ npm run build

FROM ghcr.io/home-assistant/base:latest

ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=0.1.0

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}"

ENV \
    DATABASE_URL="sqlite:////data/noko_tracker.db" \
    NOKO_STATIC_DIR="/app/frontend" \
    PATH="/opt/noko-tracker/bin:${PATH}" \
    PYTHONUNBUFFERED="1"

COPY backend/requirements.txt /tmp/requirements.txt

RUN \
    apk add --no-cache \
        libffi \
        libstdc++ \
        openssl \
        py3-pip \
        py3-virtualenv \
        python3 \
    && apk add --no-cache --virtual .build-deps \
        build-base \
        cargo \
        libffi-dev \
        openssl-dev \
        python3-dev \
    && python3 -m venv /opt/noko-tracker \
    && /opt/noko-tracker/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/noko-tracker/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && apk del .build-deps \
    && rm -f /tmp/requirements.txt

WORKDIR /app

COPY backend /app/backend
COPY --from=frontend-build /build/frontend/dist /app/frontend
COPY run.sh /run.sh

RUN chmod a+x /run.sh

EXPOSE 8000

CMD ["/run.sh"]
