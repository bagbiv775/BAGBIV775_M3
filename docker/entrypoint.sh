#!/bin/sh
# Prepare the database and static files, then start the web server (CMD).
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0

if [ "${SEED_DEMO_DATA:-0}" = "1" ]; then
    python manage.py seed_demo
fi

exec "$@"
