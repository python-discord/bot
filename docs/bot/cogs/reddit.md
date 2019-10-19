# Reddit

> Auto-generated documentation for [bot.cogs.reddit](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / `Cogs` / Reddit
  - [Reddit](#reddit)
    - [Reddit().fetch_posts](#redditfetch_posts)
    - [Reddit().init_reddit_polling](#redditinit_reddit_polling)
    - [Reddit().poll_new_posts](#redditpoll_new_posts)
    - [Reddit().poll_top_weekly_posts](#redditpoll_top_weekly_posts)
    - [Reddit().send_top_posts](#redditsend_top_posts)
  - [setup](#setup)

## Reddit

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py#L19)

```python
class Reddit(bot: Bot)
```

Track subreddit posts and show detailed statistics about them.

### Reddit().fetch_posts

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py#L39)

```python
def fetch_posts(route: str) -> List[dict]
```

A helper method to fetch a certain amount of Reddit posts at a given route.

### Reddit().init_reddit_polling

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py#L267)

```python
def init_reddit_polling() -> None
```

Initiate reddit post event loop.

### Reddit().poll_new_posts

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py#L124)

```python
def poll_new_posts() -> None
```

Periodically search for new subreddit posts.

### Reddit().poll_top_weekly_posts

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py#L185)

```python
def poll_top_weekly_posts() -> None
```

Post a summary of the top posts every week.

### Reddit().send_top_posts

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py#L66)

```python
def send_top_posts(
    channel: TextChannel,
    subreddit: Subreddit,
    content: str = None,
    time: str = 'all',
) -> Message
```

Create an embed for the top posts, then send it in a given TextChannel.

#### See also

- [Subreddit](../converters.md#subreddit)

## setup

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/cogs/reddit.py#L281)

```python
def setup(bot: Bot) -> None
```

Reddit cog load.
