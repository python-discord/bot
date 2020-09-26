FROM mcr.microsoft.com/vscode/devcontainers/universal:linux

USER root

WORKDIR /tmp/devcontainer
COPY . .
RUN chmod +x ./base-setup.sh ./project-setup.sh && ./base-setup.sh

WORKDIR /root/workspace/bot
RUN /tmp/devcontainer/project-setup.sh

RUN rm /tmp/devcontainer
