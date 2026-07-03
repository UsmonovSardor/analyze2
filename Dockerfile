FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY blacklion ./blacklion
RUN pip install --no-cache-dir ".[mt5]"
COPY configs ./configs

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "blacklion"]
