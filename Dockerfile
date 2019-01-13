FROM python:3.7-alpine3.7

RUN apk add --no-cache \
    build-base \
    freetype-dev \
    git \
    jpeg-dev \
    libffi-dev \
    libxml2 \
    libxml2-dev \
    libxslt-dev \
    tini \
    zlib \
    zlib-dev

ENV \
    LIBRARY_PATH=/lib:/usr/lib \
    PIPENV_HIDE_EMOJIS=1 \
    PIPENV_HIDE_EMOJIS=1 \
    PIPENV_IGNORE_VIRTUALENVS=1 \
    PIPENV_IGNORE_VIRTUALENVS=1 \
    PIPENV_NOSPIN=1 \
    PIPENV_NOSPIN=1 \
    PIPENV_VENV_IN_PROJECT=1 \
    PIPENV_VENV_IN_PROJECT=1

RUN pip install -U pipenv

WORKDIR /bot
COPY . .

RUN pipenv install --deploy --system

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["pipenv", "run", "start"]
