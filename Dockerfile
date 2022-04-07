# pull official base image
FROM python:3.9.5-alpine

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apk update \
    && apk add bash

# install gcc package
RUN apk update \
    && apk add gcc g++ make python3-dev musl-dev libffi-dev libxml2-dev libxslt-dev postgresql-dev

# copy project
COPY shylock/ /usr/src/shylock

# set work directory
WORKDIR /usr/src/shylock

# install dependencies
RUN pip install --upgrade pip
COPY requirements.txt /usr/src/shylock/
RUN pip install -r /usr/src/shylock/requirements.txt

# copy entrypoint.sh
COPY entrypoint.sh /usr/src/shylock/

# copy env vars
COPY .env /usr/src/shylock/

# run entrypoint.sh
ENTRYPOINT ["/usr/src/shylock/entrypoint.sh"]
