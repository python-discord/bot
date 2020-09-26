#! /bin/bash

pipenv sync --dev
pipenv run precommit
docker-compose pull
docker-compose build
