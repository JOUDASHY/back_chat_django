#!/bin/bash

# Convertir les retours à la ligne en format Unix
set -e

# Attendre que MySQL soit prêt
echo "⏳ Waiting for MySQL at $DB_HOST:$DB_PORT ..."
until nc -z -v -w30 "$DB_HOST" "$DB_PORT"; do
  echo "⌛ Still waiting for MySQL..."
  sleep 1
done

echo "✅ MySQL is up - launching Django..."

# Lancer les migrations et le serveur Django
python manage.py migrate --noinput
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
  