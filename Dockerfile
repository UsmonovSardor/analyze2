FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY blacklion ./blacklion
# Includes the [mt5] extra (mt5linux bridge client) so the bot can read candles
# from the Wine MT5 terminal; still runs pure dry-run when BL_MT5_DATA is unset.
RUN pip install --no-cache-dir ".[mt5]"
COPY configs ./configs

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/journal.db
CMD ["python", "-m", "blacklion"]
