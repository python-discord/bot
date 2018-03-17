#!/bin/bash

apt-get update
apt-get install -y software-properties-common
apt-get install -y python-software-properties
apt-get install -y curl
apt-get install -y apt-transport-https

# Python3.6
add-apt-repository -y ppa:jonathonf/python-3.6
apt-get update
apt-get install -y python3.6
apt-get install -y python3.6-dev
apt-get install -y build-essential
curl -s https://bootstrap.pypa.io/get-pip.py | python3.6 -
python3.6 -m pip install -r /vagrant/requirements.txt

tee /root/.bashrc <<EOF
HISTCONTROL=ignoreboth
shopt -s histappend
HISTSIZE=1000
HISTFILESIZE=2000
shopt -s checkwinsize

if [ -z "${debian_chroot:-}" ] && [ -r /etc/debian_chroot ]; then
    debian_chroot=$(cat /etc/debian_chroot)
fi

case "$TERM" in
    xterm-color|*-256color) color_prompt=yes;;
esac

PS1='${debian_chroot:+($debian_chroot)}\u@\h:\w\$ '

test -r ~/.dircolors && eval "$(dircolors -b ~/.dircolors)" || eval "$(dircolors -b)"
alias ls='ls --color=auto'
alias grep='grep --color=auto'
alias fgrep='fgrep --color=auto'
alias egrep='egrep --color=auto'
alias ll='ls -alF --color=auto'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'

export BOT_TOKEN="abcdefg"
export SITE_URL="pysite.local"
export DEPLOY_SITE_KEY="sdfsdf"
export DEPLOY_BOT_KEY="sdfsdf"
export DEPLOY_URL="https://api.beardfist.com/pythondiscord"
export STATUS_URL="https://api.beardfist.com/pdstatus"
export CLICKUP_KEY="abcdefg"
export PAPERTRAIL_ADDRESS=""
export PAPERTRAIL_PORT=""
export LOG_LEVEL=DEBUG
export SERVER_NAME="pysite.local"
export WEBPAGE_PORT="80"
export WEBPAGE_SECRET_KEY="123456789abcdefghijklmn"
export RETHINKDB_HOST="127.0.0.1"
export RETHINKDB_PORT="28016"
export RETHINKDB_DATABASE="database"
export RETHINKDB_TABLE="table"
export BOT_API_KEY="abcdefghijklmnopqrstuvwxyz"
export TEMPLATES_AUTO_RELOAD="yes"
EOF
