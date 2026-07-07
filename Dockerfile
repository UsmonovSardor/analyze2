FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY blacklion ./blacklion
# [mt5] pulls rpyc (5.x, matches the Wine server); mt5linux 0.1.9 itself is
# installed --no-deps because its requirements.txt is an un-resolvable frozen
# freeze. The bot still runs pure dry-run when BL_MT5_DATA is unset.
RUN pip install --no-cache-dir ".[mt5]" \
 && pip install --no-cache-dir --no-deps "mt5linux==0.1.9"
COPY configs ./configs

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/journal.db
CMD ["python", "-m", "blacklion"]
