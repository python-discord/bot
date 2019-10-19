# Help

> Auto-generated documentation for [bot.cogs.help](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Help
  - [Cog](#cog)
    - [Cog().commands](#cogcommands)
    - [Cog().description](#cogdescription)
    - [Cog().name](#cogname)
  - [Help](#help)
  - [HelpQueryNotFound](#helpquerynotfound)
  - [HelpSession](#helpsession)
    - [HelpSession().is_first_page](#helpsessionis_first_page)
    - [HelpSession().is_last_page](#helpsessionis_last_page)
    - [HelpSession().add_reactions](#helpsessionadd_reactions)
    - [HelpSession().build_pages](#helpsessionbuild_pages)
    - [HelpSession().do_back](#helpsessiondo_back)
    - [HelpSession().do_end](#helpsessiondo_end)
    - [HelpSession().do_first](#helpsessiondo_first)
    - [HelpSession().do_next](#helpsessiondo_next)
    - [HelpSession().do_stop](#helpsessiondo_stop)
    - [HelpSession().embed_page](#helpsessionembed_page)
    - [HelpSession().on_message_delete](#helpsessionon_message_delete)
    - [HelpSession().on_reaction_add](#helpsessionon_reaction_add)
    - [HelpSession().prepare](#helpsessionprepare)
    - [HelpSession().reset_timeout](#helpsessionreset_timeout)
    - [HelpSession.start](#helpsessionstart)
    - [HelpSession().stop](#helpsessionstop)
    - [HelpSession().timeout](#helpsessiontimeout)
    - [HelpSession().update_page](#helpsessionupdate_page)
  - [setup](#setup)
  - [teardown](#teardown)
  - [unload](#unload)

## Cog

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L1)

```python
class Cog()
```

Cog(name, description, commands)

### Cog().commands

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L1)

```python
#property getter
def operator.itemgetter(2)()
```

Alias for field number 2

### Cog().description

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L1)

```python
#property getter
def operator.itemgetter(1)()
```

Alias for field number 1

### Cog().name

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L1)

```python
#property getter
def operator.itemgetter(0)()
```

Alias for field number 0

## Help

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L504)

```python
class Help()
```

Custom Embed Pagination Help feature.

## HelpQueryNotFound

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L32)

```python
class HelpQueryNotFound(arg: str, possible_matches: dict = None)
```

Raised when a HelpSession Query doesn't match a command or cog.

Contains the custom attribute of ``possible_matches``.

Instances of this object contain a dictionary of any command(s) that were close to matching the
query, where keys are the possible matched command names and values are the likeness match scores.

## HelpSession

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L47)

```python
class HelpSession(ctx: Context, command)
```

An interactive session for bot and command help output.

Expected attributes include:
    * title: str
        The title of the help message.
    * query: Union[discord.ext.commands.Bot, discord.ext.commands.Command]
    * description: str
        The description of the query.
    * pages: list[str]
        A list of the help content split into manageable pages.
    * message: `discord.Message`
        The message object that's showing the help contents.
    * destination: `discord.abc.Messageable`
        Where the help message is to be sent to.

Cogs can be grouped into custom categories. All cogs with the same category will be displayed
under a single category name in the help output. Custom categories are defined inside the cogs
as a class attribute named `category`. A description can also be specified with the attribute
`category_description`. If a description is not found in at least one cog, the default will be
the regular description (class docstring) of the first cog found in the category.

### HelpSession().is_first_page

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L47)

```python
#property getter
def is_first_page() -> bool
```

Check if session is currently showing the first page.

### HelpSession().is_last_page

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L47)

```python
#property getter
def is_last_page() -> bool
```

Check if the session is currently showing the last page.

### HelpSession().add_reactions

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L217)

```python
def add_reactions() -> None
```

Adds the relevant reactions to the help message based on if pagination is required.

### HelpSession().build_pages

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L279)

```python
def build_pages() -> None
```

Builds the list of content pages to be paginated through in the help message, as a list of str.

### HelpSession().do_back

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L484)

```python
def do_back() -> None
```

Event that is called when the user requests the previous page.

### HelpSession().do_end

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L494)

```python
def do_end() -> None
```

Event that is called when the user requests the last page.

### HelpSession().do_first

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L479)

```python
def do_first() -> None
```

Event that is called when the user requests the first page.

### HelpSession().do_next

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L489)

```python
def do_next() -> None
```

Event that is called when the user requests the next page.

### HelpSession().do_stop

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L499)

```python
def do_stop() -> None
```

Event that is called when the user requests to stop the help session.

### HelpSession().embed_page

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L407)

```python
def embed_page(page_number: int = 0) -> Embed
```

Returns an Embed with the requested page formatted within.

### HelpSession().on_message_delete

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L199)

```python
def on_message_delete(message: Message) -> None
```

Closes the help session when the help message is deleted.

### HelpSession().on_reaction_add

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L172)

```python
def on_reaction_add(reaction: Reaction, user: User) -> None
```

Event handler for when reactions are added on the help message.

### HelpSession().prepare

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L204)

```python
def prepare() -> None
```

Sets up the help session pages, events, message and reactions.

### HelpSession().reset_timeout

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L162)

```python
def reset_timeout() -> None
```

Cancels the original timeout task and sets it again from the start.

### HelpSession.start

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L437)

```python
def start(ctx: Context, command, options) -> HelpSession
```

Create and begin a help session based on the given command context.

Available options kwargs:
    * cleanup: Optional[bool]
        Set to `True` to have the message deleted on session end. Defaults to `False`.
    * only_can_run: Optional[bool]
        Set to `True` to hide commands the user can't run. Defaults to `False`.
    * show_hidden: Optional[bool]
        Set to `True` to include hidden commands. Defaults to `False`.
    * max_lines: Optional[int]
        Sets the max number of lines the paginator will add to a single page. Defaults to 20.

### HelpSession().stop

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L457)

```python
def stop() -> None
```

Stops the help session, removes event listeners and attempts to delete the help message.

### HelpSession().timeout

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L157)

```python
def timeout(seconds: int = 30) -> None
```

Waits for a set number of seconds, then stops the help session.

### HelpSession().update_page

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L427)

```python
def update_page(page_number: int = 0) -> None
```

Sends the intial message, or changes the existing one to the given page number.

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L535)

```python
def setup(bot: Bot) -> None
```

The setup for the help extension.

This is called automatically on `bot.load_extension` being run.

Stores the original help command instance on the `bot._old_help` attribute for later
reinstatement, before removing it from the command registry so the new help command can be
loaded successfully.

If an exception is raised during the loading of the cog, [unload](#unload) will be called in order to
reinstate the original help command.

## teardown

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L558)

```python
def teardown(bot: Bot) -> None
```

The teardown for the help extension.

This is called automatically on `bot.unload_extension` being run.

Calls [unload](#unload) in order to reinstate the original help command.

## unload

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/help.py#L525)

```python
def unload(bot: Bot) -> None
```

Reinstates the original help command.

This is run if the cog raises an exception on load, or if the extension is unloaded.
