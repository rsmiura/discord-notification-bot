FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 botuser \
    && mkdir /data && chown botuser:botuser /data

COPY bot.py commands.py config.py notifications.py state.py ./
COPY monitors/ ./monitors/

USER botuser
VOLUME ["/data"]
CMD ["python", "bot.py"]
