FROM python:3.13-alpine

WORKDIR /app
COPY --chown=1000:1000 src/ ./src/

USER 1000

CMD ["python", "-m", "src.server"]
