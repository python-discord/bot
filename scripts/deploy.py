import os

import requests

url = os.environ.get("AUTODEPLOY_WEBHOOK")
token = os.environ.get("AUTODEPLOY_TOKEN")
result = requests.get(url=url, headers={"token": token})
print(result.text)
