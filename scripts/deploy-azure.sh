#!/bin/bash

cd ..

# Build and deploy on master branch, only if not a pull request
if [[ ($BUILD_SOURCEBRANCHNAME == 'master') && ($SYSTEM_PULLREQUEST_PULLREQUESTID == '') ]]; then
    echo "Building image"
    docker build -t pythondiscord/bot:latest .

    echo "Pushing image"
    docker push pythondiscord/bot:latest
fi
