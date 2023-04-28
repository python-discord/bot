---
embed:
    title: "Message Content Intent"
---

The discord gateway only dispatches events you subscribe to, which you can configure by using "intents"

The message content intent is what determines if an app will receive the content of an ``on_message_create`` event.

Disabling or enabling this feature will allow or disallow this data to be received.

Discord has disabled this permission for verified bots (bots verified over 75-100 servers).

Users can request this permission for their bot.
