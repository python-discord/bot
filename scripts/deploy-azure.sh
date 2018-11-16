#!/bin/bash

cd ..

# Build and deploy on master branch, only if not a pull request
if [[ ($BUILD_SOURCEBRANCHNAME == 'master') && ($SYSTEM_PULLREQUEST_PULLREQUESTID == '') ]]; then
    changed_lines=$(git diff HEAD~1 HEAD docker/base.Dockerfile | wc -l)

    if [ $changed_lines != '0' ]; then
      echo "base.Dockerfile was changed"

      echo "Building bot base"
      docker build -t pythondiscord/bot-base:latest -f docker/base.Dockerfile .

      echo "Pushing image to Docker Hub"
      docker push pythondiscord/bot-base:latest
    else
      echo "base.Dockerfile was not changed, not building"
    fi

    echo "Building image"
    docker build -t pythondiscord/bot:latest -f docker/bot.Dockerfile .

    echo "Pushing image"
    docker push pythondiscord/bot:latest

    echo "Deploying container"
    curl -H "token: $1" $2
else
    echo "Skipping deploy"
fi