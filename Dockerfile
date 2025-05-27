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

# Configurer le répertoire de travail
WORKDIR /app

# Copier d'abord l'entrypoint et définir les permissions
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Installer les dépendances Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copier le reste du code
COPY . .

EXPOSE 8000

CMD ["/app/entrypoint.sh"]