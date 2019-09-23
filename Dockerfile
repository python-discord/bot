FROM python:3.7-slim

# Set pip to have cleaner logs and no saved cache
ENV PIP_NO_CACHE_DIR=false \
    PIPENV_HIDE_EMOJIS=1 \
    PIPENV_IGNORE_VIRTUALENVS=1 \
    PIPENV_NOSPIN=1

# Install pipenv
RUN pip install -U pipenv

# Copy project files into working directory
WORKDIR /bot
COPY docker .

# Install project dependencies
RUN pipenv install --system --deploy

ENTRYPOINT ["python3"]
CMD ["-m", "bot"]
