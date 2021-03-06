FROM python:3.8-slim

# Set pip to have cleaner logs and no saved cache
ENV PIP_NO_CACHE_DIR=false \
    PIPENV_HIDE_EMOJIS=1 \
    PIPENV_IGNORE_VIRTUALENVS=1 \
    PIPENV_NOSPIN=1

RUN apt-get -y update \
    && apt-get install -y \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install pipenv
RUN pip install -U pipenv

# Create the working directory
WORKDIR /bot

# Install project dependencies
COPY Pipfile* ./
RUN pipenv install --system --deploy

# Define Git SHA build argument
ARG git_sha="development"

# Set Git SHA environment variable for Sentry
ENV GIT_SHA=$git_sha

# Copy the source code in last to optimize rebuilding the image
COPY . .

ENTRYPOINT ["python3"]
CMD ["-m", "bot"]
