FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY blacklion ./blacklion
# Base deps only (PaperBroker + Yahoo dry-run). Add ".[mt5]" once a broker is wired.
RUN pip install --no-cache-dir .
COPY configs ./configs

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/journal.db
CMD ["python", "-m", "blacklion"]
