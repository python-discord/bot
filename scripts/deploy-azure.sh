#!/bin/bash

cd ..

# Build and deploy on django branch, only if not a pull request
if [[ ($BUILD_SOURCEBRANCHNAME == 'django') && ($SYSTEM_PULLREQUEST_PULLREQUESTID == '') ]]; then
    echo "Building image"
    docker build -t pythondiscord/bot:django .

    echo "Pushing image"
    docker push pythondiscord/bot:django
fi
