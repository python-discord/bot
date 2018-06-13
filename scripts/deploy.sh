#!/bin/bash

# Build and deploy on master branch
if [[ $CI_COMMIT_REF_SLUG == 'master' ]]; then
    echo "Connecting to docker hub"
    echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin

    changed_lines=$(git diff HEAD~1 HEAD docker/Dockerfile.base | wc -l)

    if [ $changed_lines != '0' ]; then
      echo "Dockerfile.base was changed"

      echo "Building bot base"
      docker build -t pythondiscord/bot-base:latest -f docker/Dockerfile.base .

      echo "Pushing image to Docker Hub"
      docker push pythondiscord/bot-base:latest
    else
      echo "Dockerfile.base was not changed, not building"
    fi

    echo "Building image"
    docker build -t pythondiscord/bot:latest -f docker/Dockerfile .

    echo "Pushing image"
    docker push pythondiscord/bot:latest

    echo "Deploying container"
    curl -H "token: $AUTODEPLOY_TOKEN" $AUTODEPLOY_WEBHOOK
else
    echo "Skipping deploy"
fi
