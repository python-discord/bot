import re

MESSAGE_ID_RE = re.compile(r'(?P<message_id>[0-9]{15,20})$')
