# Decorators

> Auto-generated documentation for [bot.decorators](https://github.com/python-discord/bot/blob/master/bot/decorators.py) module.

- [Index](../README.md#modules) / [Bot](index.md#bot) / Decorators
  - [InChannelCheckFailure](#inchannelcheckfailure)
  - [in_channel](#in_channel)
  - [locked](#locked)
  - [redirect_output](#redirect_output)
  - [respect_role_hierarchy](#respect_role_hierarchy)
  - [with_role](#with_role)
  - [without_role](#without_role)

## InChannelCheckFailure

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/decorators.py#L20)

```python
class InChannelCheckFailure(channels: int)
```

Raised when a check fails for a message being sent in a whitelisted channel.

## in_channel

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/decorators.py#L30)

```python
def in_channel(channels: int) -> Callable
```

Checks that the message is in a whitelisted channel or optionally has a bypass role.

## locked

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/decorators.py#L69)

```python
def locked() -> Callable
```

Allows the user to only run one instance of the decorated command at a time.

Subsequent calls to the command from the same author are ignored until the command has completed invocation.

This decorator must go before (below) the `command` decorator.

## redirect_output

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/decorators.py#L101)

```python
def redirect_output(
    destination_channel: int,
    bypass_roles: Container[int] = None,
) -> Callable
```

Changes the channel in the context of the command to redirect the output to a certain channel.

Redirect is bypassed if the author has a role to bypass redirection.

This decorator must go before (below) the `command` decorator.

## respect_role_hierarchy

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/decorators.py#L149)

```python
def respect_role_hierarchy(target_arg: Union[int, str] = 0) -> Callable
```

Ensure the highest role of the invoking member is greater than that of the target member.

If the condition fails, a warning is sent to the invoking context. A target which is not an
instance of discord.Member will always pass.

A value of 0 (i.e. position 0) for `target_arg` corresponds to the argument which comes after
`ctx`. If the target argument is a kwarg, its name can instead be given.

This decorator must go before (below) the `command` decorator.

## with_role

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/decorators.py#L54)

```python
def with_role(role_ids: int) -> Callable
```

Returns True if the user has any one of the roles in role_ids.

## without_role

[🔍 find in source code](https://github.com/python-discord/bot/blob/master/bot/decorators.py#L62)

```python
def without_role(role_ids: int) -> Callable
```

Returns True if the user does not have any of the roles in role_ids.
