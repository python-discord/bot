import os

import requests


branch = os.environ.get("TRAVIS_BRANCH")
url = os.environ.get("AUTODEPLOY_WEBHOOK")
token = os.environ.get("AUTODEPLOY_TOKEN")
PR = os.environ.get("TRAVIS_PULL_REQUEST")

print('branch:', branch)
print('is_pr:', PR)

if branch == 'master' and PR == 'false':
    print("deploying..")
    result = requests.get(url=url, headers={'token': token})
    print(result.text)

else:
    print("skipping deploy")
