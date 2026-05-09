# --- build ---
FROM node:20-alpine AS build

WORKDIR /app
ENV CI=true

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .

# REACT_APP_BACKEND_URL is baked at build time — pass via --build-arg
ARG REACT_APP_BACKEND_URL=http://localhost:8001
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

RUN yarn build

# --- serve ---
FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
