# entrypoint.sh
#!/bin/bash
set -e

echo "⏳ Waiting for MySQL at $DB_HOST:$DB_PORT ..."
until nc -z -v -w30 "$DB_HOST" "$DB_PORT"; do
  echo "⌛ Still waiting for MySQL..."
  sleep 1
done

echo "✅ MySQL is up - launching Django..."

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
