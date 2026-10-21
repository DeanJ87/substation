# SubStation web UI: the built React app served by Caddy, which also proxies /api and /_allauth to the API.
#   docker build -f docker/frontend.Dockerfile -t substation-frontend:dev .
FROM node:22-bookworm-slim AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY specs/001-ingest-catalogue/contracts/openapi.yaml /src/specs/001-ingest-catalogue/contracts/openapi.yaml
RUN npm run api:gen && npm run build

FROM caddy:2.11.4-alpine
# security fixes released since the base image was built (005-DR-27: no fixable critical vulnerability ships)
RUN apk upgrade --no-cache
COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/frontend/dist /srv
# run unprivileged: Caddy listens on 8080 and only needs to write its /data and /config dirs
RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app app \
 && mkdir -p /data /config && chown -R app:app /data /config
USER app
EXPOSE 8080
