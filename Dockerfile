FROM python:3.11-slim

# Installer les dépendances nécessaires, y compris mariadb-client et netcat
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    mariadb-client \
    netcat-openbsd \
  && rm -rf /var/lib/apt/lists/*

# Configurer le répertoire de travail
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

COPY . ./
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

CMD ["bash", "-c", "\
  until nc -z -v -w30 mysql 3306; do echo 'Waiting for MySQL...'; sleep 1; done; \
  python manage.py migrate --noinput && \
  python manage.py collectstatic --noinput && \
  gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3"]