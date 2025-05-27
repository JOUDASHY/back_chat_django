FROM python:3.11-slim

# Installer les dépendances nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    mariadb-client \
    netcat-openbsd \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn

COPY . .

EXPOSE 8000

CMD bash -c '\
    echo "⏳ Waiting for MySQL at $DB_HOST:$DB_PORT ..." && \
    until nc -z -v -w30 "$DB_HOST" "$DB_PORT"; do \
        echo "⌛ Still waiting for MySQL..." && \
        sleep 1; \
    done && \
    echo "✅ MySQL is up - launching Django..." && \
    python manage.py migrate --noinput && \
    python manage.py collectstatic --noinput && \
    gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3'