FROM node:22.23.1-trixie-slim
WORKDIR /frontend
COPY package*.json ./
COPY . .
RUN npm install
EXPOSE 3000
CMD ["npm", "start"]