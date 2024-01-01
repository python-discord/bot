---
embed:
    title: "Using .env files in Python"
---
`.env` (dotenv) files are a type of file commonly used for storing application secrets and variables, for example API tokens and URLs, although they may also be used for storing other configurable values. While they are commonly used for storing secrets, at a high level their purpose is to load environment variables into a program.

Dotenv files are especially suited for storing secrets as they are a key-value store in a file, which can be easily loaded in most programming languages and ignored by version control systems like Git with a single entry in a `.gitignore` file.

In Python you can use dotenv files with the [`python-dotenv`](https://pypi.org/project/python-dotenv) module from PyPI, which can be installed with `pip install python-dotenv`. To use dotenv files you'll first need a file called `.env`, with content such as the following:
```
TOKEN=a00418c85bff087b49f23923efe40aa5
```
Next, in your main Python file, you need to load the environment variables from the dotenv file you just created:
```py
from dotenv import load_dotenv

load_dotenv()
```
The variables from the file have now been loaded into your program's environment, and you can access them using `os.getenv()` anywhere in your program, like this:
```py
from os import getenv

my_token = getenv("TOKEN")
```
For further reading about tokens and secrets, please read [this explanation](https://tutorial.vco.sh/tips/tokens/).
