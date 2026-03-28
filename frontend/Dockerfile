# --- Build stage ---
FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci --silent

COPY . .

# Accept VITE env vars as build args so they are baked into the JS bundle
ARG VITE_API_BASE_URL=""
ARG VITE_WS_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_BASE_URL=$VITE_WS_BASE_URL

RUN npm run build

# --- Production stage ---
FROM nginx:1.25-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
