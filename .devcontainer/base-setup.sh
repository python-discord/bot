#! /bin/bash

PYTHON_PROJECT_VERSION=3.8.1

set -e

if [ ! -d "/var/lib/apt/lists" ] || [ "$(ls /var/lib/apt/lists/ | wc -l)" = "0" ]; then
    echo "Running apt-get update..."
    apt-get update
else
    echo "Skipping apt-get update."
fi

# Process install list
install-list() {
    list="$1"
    function="$2"

    cat "$list" | while read -r line || [[ -n $line ]];
    do
        if [[ $line != "#"* ]] && [[ -n $line ]]
        then
            "$function" "$line"
        fi
    done
}

install-apt-package() {
  echo "Installing $1 with apt..."
  apt-get install -y "$1"
}

install-python-version() {
  echo "Installing Python $1..."
  pyenv install "$1"
}

install-pip-package() {
  echo "Installing $1 with pip..."
  pip install -U "$1"
}

install-list ./apt-packages install-apt-package

curl https://pyenv.run | bash
cat >> ~/.bashrc << "EOF"
export PATH="/root/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
EOF
. ~/.bashrc
install-list ./python-versions install-python-version
pyenv global $PYTHON_PROJECT_VERSION
echo "Using python interpreter $(pyenv version)"


install-list ./pip-packages install-pip-package
