FROM node:22-slim AS builder
WORKDIR /app
COPY package.json build.js ./
RUN npm install
COPY src/ src/
RUN mkdir -p server/static/dist && npm run build

FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ server/
COPY --from=builder /app/server/static/dist/ server/static/dist/

ENV FLASK_PORT=5000
ENV DATA_DIR=/app/data
VOLUME /app/data
EXPOSE 5000

CMD gunicorn --worker-class gthread --workers 1 --threads 8 --timeout 120 -b 0.0.0.0:${FLASK_PORT:-5000} "server:create_app()"
