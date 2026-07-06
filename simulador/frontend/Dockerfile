# frontend/Dockerfile
# ETAPA 1: Construcción (Build)
FROM node:20-alpine as builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# ETAPA 2: Servidor de Producción (Nginx)
FROM nginx:alpine
# Borramos la config por defecto de Nginx
RUN rm -rf /etc/nginx/conf.d/*
# Copiamos nuestra configuración
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Copiamos los archivos compilados de React
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]