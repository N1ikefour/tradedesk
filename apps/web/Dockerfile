# Статический фронт для профиля prod (SPEC.md 11.1). В local используется vite dev-сервер
# из docker-compose.yml, этот образ там не собирается.
FROM node:22-alpine AS build
WORKDIR /srv/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM nginx:1.27-alpine
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /srv/apps/web/dist /usr/share/nginx/html
EXPOSE 80
