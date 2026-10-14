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
EXPOSE 8080
