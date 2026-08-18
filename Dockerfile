FROM node:22-alpine

WORKDIR /app
COPY --chown=node:node server.js .

USER node

CMD ["node", "server.js"]