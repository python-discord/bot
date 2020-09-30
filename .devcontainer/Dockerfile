FROM mcr.microsoft.com/vscode/devcontainers/universal:linux

USER root

WORKDIR /tmp/devcontainer
COPY . .
RUN chmod +x ./base-setup.sh && ./base-setup.sh
