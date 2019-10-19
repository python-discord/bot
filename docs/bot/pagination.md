# Pagination

> Auto-generated documentation for [bot.pagination](https://github.com/python-discord/bot/blob/master/bot/pagination.py) module.

- [Index](../README.md#modules) / [Bot](index.md#bot) / Pagination
  - [EmptyPaginatorEmbed](#emptypaginatorembed)
  - [ImagePaginator](#imagepaginator)
    - [ImagePaginator().add_image](#imagepaginatoradd_image)
    - [ImagePaginator().add_line](#imagepaginatoradd_line)
    - [ImagePaginator.paginate](#imagepaginatorpaginate)
  - [LinePaginator](#linepaginator)
    - [LinePaginator().add_line](#linepaginatoradd_line)
    - [LinePaginator.paginate](#linepaginatorpaginate)

## EmptyPaginatorEmbed

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L20)

```python
class EmptyPaginatorEmbed()
```

Raised when attempting to paginate with empty contents.

## ImagePaginator

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L286)

```python
class ImagePaginator(prefix: str = '', suffix: str = '')
```

Helper class that paginates images for embeds in messages.

Close resemblance to LinePaginator, except focuses on images over text.

Refer to ImagePaginator.paginate for documentation on how to use.

### ImagePaginator().add_image

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L310)

```python
def add_image(image: str = None) -> None
```

Adds an image to a page.

### ImagePaginator().add_line

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L301)

```python
def add_line(line: str = '') -> None
```

Adds a line to each page.

### ImagePaginator.paginate

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L314)

```python
def paginate(
    pages: List[Tuple[str, str]],
    ctx: Context,
    embed: Embed,
    prefix: str = '',
    suffix: str = '',
    timeout: int = 300,
    exception_on_empty_embed: bool = False,
) -> Union[discord.message.Message, NoneType]
```

Use a paginator and set of reactions to provide pagination over a set of title/image pairs.

The reactions are used to switch page, or to finish with pagination.

When used, this will send a message using `ctx.send()` and apply a set of reactions to it. These reactions may
be used to change page, or to remove pagination from the message.

- `Note` - Pagination will be removed automatically if no reaction is added for five minutes (300 seconds).

#### Examples

```python
>>> embed = Embed()
>>> embed.set_author(name="Some Operation", url=url, icon_url=icon)
>>> await ImagePaginator.paginate(pages, ctx, embed)
```

## LinePaginator

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L26)

```python
class LinePaginator(
    prefix: str = '```',
    suffix: str = '```',
    max_size: int = 2000,
    max_lines: int = None,
) -> None
```

A class that aids in paginating code blocks for Discord messages.

Available attributes include:
* prefix: `str`
    The prefix inserted to every page. e.g. three backticks.
* suffix: `str`
    The suffix appended at the end of every page. e.g. three backticks.
* max_size: `int`
    The maximum amount of codepoints allowed in a page.
* max_lines: `int`
    The maximum amount of lines allowed in a page.

### LinePaginator().add_line

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L58)

```python
def add_line(line: str = '') -> None
```

Adds a line to the current page.

If the line exceeds the `self.max_size` then an exception is raised.

This function overrides the `Paginator.add_line` from inside `discord.ext.commands`.

It overrides in order to allow us to configure the maximum number of lines per page.

### LinePaginator.paginate

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/pagination.py#L87)

```python
def paginate(
    lines: Iterable[str],
    ctx: Context,
    embed: Embed,
    prefix: str = '',
    suffix: str = '',
    max_lines: Union[int, NoneType] = None,
    max_size: int = 500,
    empty: bool = True,
    restrict_to_user: User = None,
    timeout: int = 300,
    footer_text: str = None,
    url: str = None,
    exception_on_empty_embed: bool = False,
) -> Union[discord.message.Message, NoneType]
```

Use a paginator and set of reactions to provide pagination over a set of lines.

The reactions are used to switch page, or to finish with pagination.

When used, this will send a message using `ctx.send()` and apply a set of reactions to it. These reactions may
be used to change page, or to remove pagination from the message.

Pagination will also be removed automatically if no reaction is added for five minutes (300 seconds).

#### Examples

```python
>>> embed = Embed()
>>> embed.set_author(name="Some Operation", url=url, icon_url=icon)
>>> await LinePaginator.paginate((line for line in lines), ctx, embed)
```
