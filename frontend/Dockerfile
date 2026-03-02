# -- Build stage --
FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Exclude test files from TypeScript type-checking for production build
RUN find src -name '*.test.ts' -o -name '*.test.tsx' | xargs rm -f
RUN npm run build

# -- Serve stage --
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
