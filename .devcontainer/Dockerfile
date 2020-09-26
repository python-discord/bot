FROM mcr.microsoft.com/vscode/devcontainers/universal:linux

USER root

WORKDIR /tmp/devcontainer
COPY . .
RUN chmod +x ./setup-debian.sh && ./setup-debian.sh
