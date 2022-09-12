FROM --platform=linux/amd64 python:3.10-slim

# Define Git SHA build argument for sentry
ARG git_sha="development"

# POETRY_VIRTUALENVS_IN_PROJECT is required to ensure in-projects venvs mounted from the host in dev
# don't get prioritised by `poetry run`
ENV POETRY_VERSION=1.2.0 \
  POETRY_HOME="/opt/poetry" \
  POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_IN_PROJECT=false \
  APP_DIR="/bot" \
  GIT_SHA=$git_sha

ENV PATH="$POETRY_HOME/bin:$PATH"

RUN apt-get update \
  && apt-get -y upgrade \
  && apt-get install --no-install-recommends -y curl \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python

# Install project dependencies
WORKDIR $APP_DIR
COPY pyproject.toml poetry.lock ./
RUN poetry install --without dev

# Copy the source code in last to optimize rebuilding the image
COPY . .

ENTRYPOINT ["poetry"]
CMD ["run", "python", "-m", "bot"]
