# Stage 1: Build the Vue app
FROM node:lts-alpine as build-stage

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN npm run build

ARG VITE_API_BASE
ENV VITE_API_BASE=$VITE_API_BASE

# Stage 2: Serve with Nginx
FROM nginx:stable-alpine as production-stage
# Add this line to copy your custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build-stage /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
