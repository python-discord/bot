# Checks

> Auto-generated documentation for [bot.utils.checks](https://github.com/python-discord/bot/blob/master/bot/utils/checks.py) module.

- [Index](../../README.md#modules) / [Bot](../index.md#bot) / [Utils](index.md#utils) / Checks
  - [cooldown_with_role_bypass](#cooldown_with_role_bypass)
  - [in_channel_check](#in_channel_check)
  - [with_role_check](#with_role_check)
  - [without_role_check](#without_role_check)

## cooldown_with_role_bypass

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/checks.py#L49)

```python
def cooldown_with_role_bypass(
    rate: int,
    per: float,
    type: BucketType = <BucketType.default: 0>,
) -> Callable
```

Applies a cooldown to a command, but allows members with certain roles to be ignored.

NOTE: this replaces the `Command.before_invoke` callback, which *might* introduce problems in the future.

## in_channel_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/checks.py#L41)

```python
def in_channel_check(ctx: Context, channel_id: int) -> bool
```

Checks if the command was executed inside of the specified channel.

## with_role_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/checks.py#L10)

```python
def with_role_check(ctx: Context, role_ids: int) -> bool
```

Returns True if the user has any one of the roles in role_ids.

## without_role_check

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/utils/checks.py#L27)

```python
def without_role_check(ctx: Context, role_ids: int) -> bool
```

Returns True if the user does not have any of the roles in role_ids.
