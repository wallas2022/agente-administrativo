# Build context: src/ui/ (ver infra/compose.yml, build.context: ../src/ui).
# Imagen única (sin etapa nginx separada): `vite preview` alcanza para el
# volumen de este piloto; si el tráfico lo justifica más adelante, esto puede
# pasar a una segunda etapa con un servidor estático dedicado.
FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Vite incrusta las variables VITE_* en el bundle en tiempo de build, no en
# runtime — por eso se reciben como build arg, no como variable de entorno
# del contenedor (ver infra/compose.yml, ui.build.args).
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
