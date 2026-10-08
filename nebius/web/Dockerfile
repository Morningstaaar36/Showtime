# Showtime web image: static build served by nginx (much lighter than a dev server).
FROM node:22-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --maxsockets=4
COPY . .
RUN NODE_OPTIONS=--max-old-space-size=1536 npx vite build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
