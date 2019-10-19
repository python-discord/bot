# Bot

> Auto-generated documentation for [bot](https://github.com/python-discord/bot/blob/master/bot/__init__.py) module.

- [Index](../README.md#modules) / Bot
  - [monkeypatch_trace](#monkeypatch_trace)
  - Modules
    - [Api](api.md#api)
    - Cogs
      - [Alias](cogs/alias.md#alias)
      - [AntiSpam](cogs/antispam.md#antispam)
      - [Bot](cogs/bot.md#bot)
      - [Clean](cogs/clean.md#clean)
      - [Defcon](cogs/defcon.md#defcon)
      - [Doc](cogs/doc.md#doc)
      - [ErrorHandler](cogs/error_handler.md#errorhandler)
      - [Eval](cogs/eval.md#eval)
      - [Extensions](cogs/extensions.md#extensions)
      - [Filtering](cogs/filtering.md#filtering)
      - [Free](cogs/free.md#free)
      - [Help](cogs/help.md#help)
      - [Information](cogs/information.md#information)
      - [Jams](cogs/jams.md#jams)
      - [Logging](cogs/logging.md#logging)
      - [Moderation](cogs/moderation/index.md#moderation)
        - [Infractions](cogs/moderation/infractions.md#infractions)
        - [Management](cogs/moderation/management.md#management)
        - [ModLog](cogs/moderation/modlog.md#modlog)
        - [Superstarify](cogs/moderation/superstarify.md#superstarify)
        - [Utils](cogs/moderation/utils.md#utils)
      - [OffTopicNames](cogs/off_topic_names.md#offtopicnames)
      - [Reddit](cogs/reddit.md#reddit)
      - [Reminders](cogs/reminders.md#reminders)
      - [Security](cogs/security.md#security)
      - [Site](cogs/site.md#site)
      - [Snekbox](cogs/snekbox.md#snekbox)
      - [Sync](cogs/sync/index.md#sync)
        - [Cog](cogs/sync/cog.md#cog)
        - [Syncers](cogs/sync/syncers.md#syncers)
      - [Tags](cogs/tags.md#tags)
      - [TokenRemover](cogs/token_remover.md#tokenremover)
      - [Utils](cogs/utils.md#utils)
      - [Verification](cogs/verification.md#verification)
      - [Watchchannels](cogs/watchchannels/index.md#watchchannels)
        - [BigBrother](cogs/watchchannels/bigbrother.md#bigbrother)
        - [TalentPool](cogs/watchchannels/talentpool.md#talentpool)
        - [WatchChannel](cogs/watchchannels/watchchannel.md#watchchannel)
      - [Wolfram](cogs/wolfram.md#wolfram)
    - [Constants](constants.md#constants)
    - [Converters](converters.md#converters)
    - [Decorators](decorators.md#decorators)
    - [Interpreter](interpreter.md#interpreter)
    - [Pagination](pagination.md#pagination)
    - [Patches](patches/index.md#patches)
      - [Message Edited At](patches/message_edited_at.md#message-edited-at)
    - [Rules](rules/index.md#rules)
      - [Attachments](rules/attachments.md#attachments)
      - [Burst](rules/burst.md#burst)
      - [Burst Shared](rules/burst_shared.md#burst-shared)
      - [Chars](rules/chars.md#chars)
      - [Discord Emojis](rules/discord_emojis.md#discord-emojis)
      - [Duplicates](rules/duplicates.md#duplicates)
      - [Links](rules/links.md#links)
      - [Mentions](rules/mentions.md#mentions)
      - [Newlines](rules/newlines.md#newlines)
      - [Role Mentions](rules/role_mentions.md#role-mentions)
    - [Utils](utils/index.md#utils)
      - [Checks](utils/checks.md#checks)
      - [Messages](utils/messages.md#messages)
      - [Scheduling](utils/scheduling.md#scheduling)
      - [Time](utils/time.md#time)

## monkeypatch_trace

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/__init__.py#L13)

```python
def monkeypatch_trace(msg: str, args, kwargs) -> None
```

Log 'msg % args' with severity 'TRACE'.

To pass exception information, use the keyword argument exc_info with
a true value, e.g.

logger.trace("Houston, we have an %s", "interesting problem", exc_info=1)
