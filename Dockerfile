FROM python:3.11-slim

# Installer les dépendances nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    pkg-config \
    libssl-dev \
    mariadb-client \
    netcat-openbsd \
    git \
  && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root
RUN useradd -m -s /bin/bash appuser

# Configurer le répertoire de travail et les permissions
WORKDIR /app
COPY . /app/

# Définir les permissions
RUN chown -R appuser:appuser /app \
    && chmod +x /app/entrypoint.sh

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install gunicorn

# Passer à l'utilisateur non-root
USER appuser

EXPOSE 8000

CMD ["/app/entrypoint.sh"]