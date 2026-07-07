FROM node:22.23.1-trixie-slim
WORKDIR /backend
COPY package*.json ./
COPY . .
RUN apt-get update
RUN apt-get upgrade -y
RUN npm install
RUN npm install mongodb
RUN npm audit fix --force
EXPOSE 3001
CMD ["node", "index.js"]