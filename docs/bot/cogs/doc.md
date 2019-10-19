# Doc

> Auto-generated documentation for [bot.cogs.doc](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Doc
  - [Doc](#doc)
    - [Doc().get_symbol_embed](#docget_symbol_embed)
    - [Doc().get_symbol_html](#docget_symbol_html)
    - [Doc().init_refresh_inventory](#docinit_refresh_inventory)
    - [Doc().refresh_inventory](#docrefresh_inventory)
    - [Doc().update_single](#docupdate_single)
  - [DocMarkdownConverter](#docmarkdownconverter)
    - [DocMarkdownConverter().convert_code](#docmarkdownconverterconvert_code)
    - [DocMarkdownConverter().convert_pre](#docmarkdownconverterconvert_pre)
  - [DummyObject](#dummyobject)
  - [InventoryURL](#inventoryurl)
    - [InventoryURL.convert](#inventoryurlconvert)
  - [SphinxConfiguration](#sphinxconfiguration)
  - [async_cache](#async_cache)
  - [markdownify](#markdownify)
  - [setup](#setup)

## Doc

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L121)

```python
class Doc(bot: Bot)
```

A set of commands for querying & displaying documentation.

### Doc().get_symbol_embed

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L44)

```python
def get_symbol_embed(args) -> Union[discord.embeds.Embed, NoneType]
```

Attempt to scrape and fetch the data for the given `symbol`, and build an embed from its contents.

If the symbol is known, an Embed with documentation about it is returned.

### Doc().get_symbol_html

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L188)

```python
def get_symbol_html(symbol: str) -> Union[Tuple[str, str], NoneType]
```

Given a Python symbol, return its signature and description.

Returns a tuple in the form (str, str), or `None`.

The first tuple element is the signature of the given symbol as a markup-free string, and
the second tuple element is the description of the given symbol with HTML markup included.

If the given symbol could not be found, returns `None`.

### Doc().init_refresh_inventory

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L131)

```python
def init_refresh_inventory() -> None
```

Refresh documentation inventory on cog initialization.

### Doc().refresh_inventory

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L164)

```python
def refresh_inventory() -> None
```

Refresh internal documentation inventory.

### Doc().update_single

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L136)

```python
def update_single(
    package_name: str,
    base_url: str,
    inventory_url: str,
    config: SphinxConfiguration,
) -> None
```

Rebuild the inventory for a single package.

Where:
    * `package_name` is the package name to use, appears in the log
    * `base_url` is the root documentation URL for the specified package, used to build
        absolute paths that link to specific symbols
    * `inventory_url` is the absolute URL to the intersphinx inventory, fetched by running
        `intersphinx.fetch_inventory` in an executor on the bot's event loop
    * `config` is a [SphinxConfiguration](#sphinxconfiguration) instance to mock the regular sphinx
        project layout, required for use with intersphinx

#### See also

- [SphinxConfiguration](#sphinxconfiguration)

## DocMarkdownConverter

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L60)

```python
class DocMarkdownConverter(options)
```

Subclass markdownify's MarkdownCoverter to provide custom conversion methods.

### DocMarkdownConverter().convert_code

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L63)

```python
def convert_code(el: PageElement, text: str) -> str
```

Undo [markdownify](#markdownify)s underscore escaping.

### DocMarkdownConverter().convert_pre

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L67)

```python
def convert_pre(el: PageElement, text: str) -> str
```

Wrap any codeblocks in `py` for syntax highlighting.

## DummyObject

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L78)

```python
class DummyObject()
```

A dummy object which supports assigning anything, which the builtin `object()` does not support normally.

## InventoryURL

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L90)

```python
class InventoryURL()
```

Represents an Intersphinx inventory URL.

This converter checks whether intersphinx accepts the given inventory URL, and raises
`BadArgument` if that is not the case.

Otherwise, it simply passes through the given URL.

### InventoryURL.convert

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L100)

```python
def convert(ctx: Context, url: str) -> str
```

Convert url to Intersphinx inventory URL.

## SphinxConfiguration

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L82)

```python
class SphinxConfiguration()
```

Dummy configuration for use with intersphinx.

## async_cache

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L31)

```python
def async_cache(max_size: int = 128, arg_offset: int = 0) -> Callable
```

LRU cache implementation for coroutines.

Once the cache exceeds the maximum size, keys are deleted in FIFO order.

An offset may be optionally provided to be applied to the coroutine's arguments when creating the cache key.

## markdownify

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L73)

```python
def markdownify(html: str) -> DocMarkdownConverter
```

Create a DocMarkdownConverter object from the input html.

#### See also

- [DocMarkdownConverter](#docmarkdownconverter)

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/doc.py#L369)

```python
def setup(bot: Bot) -> None
```

Doc cog load.
