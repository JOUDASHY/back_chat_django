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

# Add execute permission to entrypoint.sh
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

EXPOSE 8000

CMD ["./entrypoint.sh"]