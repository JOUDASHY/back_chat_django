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

# Copier les dépendances Python et installer
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copier tout le code de l'application
COPY . ./

# Collecte les fichiers statiques (si nécessaire)
RUN python manage.py collectstatic --noinput || true

# Exposer le port sur lequel Django fonctionne
EXPOSE 8000

# Commande pour démarrer Django après que MySQL soit prêt
CMD ["bash", "-c", "until nc -z -v -w30 mysql 3306; do echo 'Waiting for MySQL...'; sleep 1; done; python manage.py runserver 0.0.0.0:8000"]
