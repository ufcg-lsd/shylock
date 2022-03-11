#!/bin/sh

python /usr/src/shylock/manage.py flush --no-input
python /usr/src/shylock/manage.py makemigrations
python /usr/src/shylock/manage.py migrate
python /usr/src/shylock/manage.py collectstatic --no-input --clear

exec "$@"
