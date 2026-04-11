# Stage 1: Build the React app
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy source and build
COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:stable-alpine
# Copy the build output to Nginx's html folder
COPY --from=build /app/dist /usr/share/nginx/html

# Copy a custom nginx config if you have one,
# otherwise Nginx defaults to port 80
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
