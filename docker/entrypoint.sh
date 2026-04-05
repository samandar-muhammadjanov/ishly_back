#!/bin/bash
# =============================================================================
# Docker Entrypoint Script
# Waits for dependencies then runs migrations and starts the app
# =============================================================================

set -e

echo "🚀 Starting GIG Marketplace..."

# ----------------------------
# Wait for PostgreSQL
# ----------------------------
echo "⏳ Waiting for PostgreSQL..."
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 0.5
done
echo "✅ PostgreSQL is ready!"

# ----------------------------
# Wait for Redis
# ----------------------------
REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2 | cut -d/ -f1)

echo "⏳ Waiting for Redis..."
while ! nc -z "$REDIS_HOST" "$REDIS_PORT"; do
  sleep 0.5
done
echo "✅ Redis is ready!"

# ----------------------------
# Run Migrations
# ----------------------------
echo "🔄 Running database migrations..."
python manage.py migrate --noinput

# ----------------------------
# Collect Static Files (production only)
# ----------------------------
if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.production" ]; then
  echo "📦 Collecting static files..."
  python manage.py collectstatic --noinput
fi

# ----------------------------
# Create Superuser (dev only)
# ----------------------------
if [ "$DJANGO_SETTINGS_MODULE" = "config.settings.development" ] && [ "$CREATE_SUPERUSER" = "true" ]; then
  echo "👤 Creating superuser..."
  python manage.py createsuperuser --noinput || true
fi

echo "✅ Initialization complete!"
echo "🌐 Starting server..."

exec "$@"
