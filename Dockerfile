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
    LIBRARY_PATH=/lib:/usr/lib

RUN pip install -U pipenv

WORKDIR /bot
COPY . .

RUN pipenv install --deploy --system

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python3", "-m", "bot"]
