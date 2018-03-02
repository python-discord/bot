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
