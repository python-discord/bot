FROM python:3.7-alpine3.7

RUN apk add --update tini
RUN apk add --update build-base
RUN apk add --update libffi-dev
RUN apk add --update zlib
RUN apk add --update jpeg-dev
RUN apk add --update libxml2 libxml2-dev libxslt-dev
RUN apk add --update zlib-dev
RUN apk add --update freetype-dev
RUN apk add --update git

ENV LIBRARY_PATH=/lib:/usr/lib
ENV PIPENV_VENV_IN_PROJECT=1
ENV PIPENV_IGNORE_VIRTUALENVS=1
ENV PIPENV_NOSPIN=1
ENV PIPENV_HIDE_EMOJIS=1
ENV PIPENV_VENV_IN_PROJECT=1
ENV PIPENV_IGNORE_VIRTUALENVS=1
ENV PIPENV_NOSPIN=1
ENV PIPENV_HIDE_EMOJIS=1

RUN pip install -U pipenv

RUN mkdir -p /bot
COPY . /bot
WORKDIR /bot

RUN pipenv install --deploy --system

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["pipenv", "run", "start"]
