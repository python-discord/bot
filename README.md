# Python Utility Bot

[![Discord](https://img.shields.io/discord/267624335836053506?color=%237289DA&label=Python%20Discord&logo=discord&logoColor=white)](https://discord.gg/2B963hn)
[![Build Status](https://dev.azure.com/python-discord/Python%20Discord/_apis/build/status/Bot?branchName=master)](https://dev.azure.com/python-discord/Python%20Discord/_build/latest?definitionId=1&branchName=master)
[![Tests](https://img.shields.io/azure-devops/tests/python-discord/Python%20Discord/1?compact_message)](https://dev.azure.com/python-discord/Python%20Discord/_apis/build/status/Bot?branchName=master)
[![Coverage](https://img.shields.io/azure-devops/coverage/python-discord/Python%20Discord/1/master)](https://dev.azure.com/python-discord/Python%20Discord/_apis/build/status/Bot?branchName=master)
[![License](https://img.shields.io/github/license/python-discord/bot)](LICENSE)
[![Website](https://img.shields.io/badge/website-visit-brightgreen)](https://pythondiscord.com)

This project is a Discord bot specifically for use with the Python Discord server. It provides numerous utilities
and other tools to help keep the server running like a well-oiled machine.

## Requirements

- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- [Docker](https://docs.docker.com/install/)
- [Docker-Compose](https://docs.docker.com/compose/install/)
  - `pip install docker-compose`
- [Pipenv](https://pipenv.kennethreitz.org/en/latest/install/#installing-pipenv)
  - `pip install pipenv`

## Setup Reference (temporary)

1. Read the [Contributing](CONTRIBUTING.md) guidelines.
2. Clone the repository to a suitable working project directory using [`git clone`](https://git-scm.com/docs/git-clone).
   - If you are not a core developer, you will need to [`fork`](https://help.github.com/en/articles/fork-a-repo) [pythondiscord/bot](https://github.com/python-discord/bot).
3. Create a copy of `config-default.yml` named `config.yml` and edit the configuration options.
   - This is to be replaced with different instructions in future due to upcoming config updates.
4. Create an empty `.env` in the same top-level project directory and add:
   - `BOT_TOKEN=yourdiscordbottoken`
   - If you have a development site setup already, get the docker project name and add in `.env`:
     - `COMPOSE_PROJECT_NAME=site`, adjusting `site` to match the other project name.
5. Install development dependancies for your IDE/editor/linting:
   - `pipenv sync --dev`
5. Run the compose:
   - If you're running a full development site setup already, run:
     - `docker-compose up bot`
   - Otherwise, run:
     - `docker-compose up`
