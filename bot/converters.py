import logging
import re
import typing as t
from datetime import datetime
from ssl import CertificateError

import dateutil.parser
import dateutil.tz
import discord
from aiohttp import ClientConnectorError
from dateutil.relativedelta import relativedelta
from discord.ext.commands import BadArgument, Context, Converter


log = logging.getLogger(__name__)


def allowed_strings(*values, preserve_case: bool = False) -> t.Callable[[str], str]:
    """
    Return a converter which only allows arguments equal to one of the given values.

    Unless preserve_case is True, the argument is converted to lowercase. All values are then
    expected to have already been given in lowercase too.
    """
    def converter(arg: str) -> str:
        if not preserve_case:
            arg = arg.lower()

        if arg not in values:
            raise BadArgument(f"Only the following values are allowed:\n```{', '.join(values)}```")
        else:
            return arg

    return converter


class ValidPythonIdentifier(Converter):
    """
    A converter that checks whether the given string is a valid Python identifier.

    This is used to have package names that correspond to how you would use the package in your
    code, e.g. `import package`.

    Raises `BadArgument` if the argument is not a valid Python identifier, and simply passes through
    the given argument otherwise.
    """

    @staticmethod
    async def convert(ctx: Context, argument: str) -> str:
        """Checks whether the given string is a valid Python identifier."""
        if not argument.isidentifier():
            raise BadArgument(f"`{argument}` is not a valid Python identifier")
        return argument


class ValidURL(Converter):
    """
    Represents a valid webpage URL.

    This converter checks whether the given URL can be reached and requesting it returns a status
    code of 200. If not, `BadArgument` is raised.

    Otherwise, it simply passes through the given URL.
    """

    @staticmethod
    async def convert(ctx: Context, url: str) -> str:
        """This converter checks whether the given URL can be reached with a status code of 200."""
        try:
            async with ctx.bot.http_session.get(url) as resp:
                if resp.status != 200:
                    raise BadArgument(
                        f"HTTP GET on `{url}` returned status `{resp.status}`, expected 200"
                    )
        except CertificateError:
            if url.startswith('https'):
                raise BadArgument(
                    f"Got a `CertificateError` for URL `{url}`. Does it support HTTPS?"
                )
            raise BadArgument(f"Got a `CertificateError` for URL `{url}`.")
        except ValueError:
            raise BadArgument(f"`{url}` doesn't look like a valid hostname to me.")
        except ClientConnectorError:
            raise BadArgument(f"Cannot connect to host with URL `{url}`.")
        return url


class InfractionSearchQuery(Converter):
    """A converter that checks if the argument is a Discord user, and if not, falls back to a string."""

    @staticmethod
    async def convert(ctx: Context, arg: str) -> t.Union[discord.Member, str]:
        """Check if the argument is a Discord user, and if not, falls back to a string."""
        try:
            maybe_snowflake = arg.strip("<@!>")
            return await ctx.bot.fetch_user(maybe_snowflake)
        except (discord.NotFound, discord.HTTPException):
            return arg


class Subreddit(Converter):
    """Forces a string to begin with "r/" and checks if it's a valid subreddit."""

    @staticmethod
    async def convert(ctx: Context, sub: str) -> str:
        """
        Force sub to begin with "r/" and check if it's a valid subreddit.

        If sub is a valid subreddit, return it prepended with "r/"
        """
        sub = sub.lower()

        if not sub.startswith("r/"):
            sub = f"r/{sub}"

        resp = await ctx.bot.http_session.get(
            "https://www.reddit.com/subreddits/search.json",
            params={"q": sub}
        )

        json = await resp.json()
        if not json["data"]["children"]:
            raise BadArgument(
                f"The subreddit `{sub}` either doesn't exist, or it has no posts."
            )

        return sub


class TagNameConverter(Converter):
    """
    Ensure that a proposed tag name is valid.

    Valid tag names meet the following conditions:
        * All ASCII characters
        * Has at least one non-whitespace character
        * Not solely numeric
        * Shorter than 127 characters
    """

    @staticmethod
    async def convert(ctx: Context, tag_name: str) -> str:
        """Lowercase & strip whitespace from proposed tag_name & ensure it's valid."""
        def is_number(value: str) -> bool:
            """Check to see if the input string is numeric."""
            try:
                float(value)
            except ValueError:
                return False
            return True

        tag_name = tag_name.lower().strip()

        # The tag name has at least one invalid character.
        if ascii(tag_name)[1:-1] != tag_name:
            log.warning(f"{ctx.author} tried to put an invalid character in a tag name. "
                        "Rejecting the request.")
            raise BadArgument("Don't be ridiculous, you can't use that character!")

        # The tag name is either empty, or consists of nothing but whitespace.
        elif not tag_name:
            log.warning(f"{ctx.author} tried to create a tag with a name consisting only of whitespace. "
                        "Rejecting the request.")
            raise BadArgument("Tag names should not be empty, or filled with whitespace.")

        # The tag name is a number of some kind, we don't allow that.
        elif is_number(tag_name):
            log.warning(f"{ctx.author} tried to create a tag with a digit as its name. "
                        "Rejecting the request.")
            raise BadArgument("Tag names can't be numbers.")

        # The tag name is longer than 127 characters.
        elif len(tag_name) > 127:
            log.warning(f"{ctx.author} tried to request a tag name with over 127 characters. "
                        "Rejecting the request.")
            raise BadArgument("Are you insane? That's way too long!")

        return tag_name


class TagContentConverter(Converter):
    """Ensure proposed tag content is not empty and contains at least one non-whitespace character."""

    @staticmethod
    async def convert(ctx: Context, tag_content: str) -> str:
        """
        Ensure tag_content is non-empty and contains at least one non-whitespace character.

        If tag_content is valid, return the stripped version.
        """
        tag_content = tag_content.strip()

        # The tag contents should not be empty, or filled with whitespace.
        if not tag_content:
            log.warning(f"{ctx.author} tried to create a tag containing only whitespace. "
                        "Rejecting the request.")
            raise BadArgument("Tag contents should not be empty, or filled with whitespace.")

        return tag_content


class Duration(Converter):
    """Convert duration strings into UTC datetime.datetime objects."""

    duration_parser = re.compile(
        r"((?P<years>\d+?) ?(years|year|Y|y) ?)?"
        r"((?P<months>\d+?) ?(months|month|m) ?)?"
        r"((?P<weeks>\d+?) ?(weeks|week|W|w) ?)?"
        r"((?P<days>\d+?) ?(days|day|D|d) ?)?"
        r"((?P<hours>\d+?) ?(hours|hour|H|h) ?)?"
        r"((?P<minutes>\d+?) ?(minutes|minute|M) ?)?"
        r"((?P<seconds>\d+?) ?(seconds|second|S|s))?"
    )

    async def convert(self, ctx: Context, duration: str) -> datetime:
        """
        Converts a `duration` string to a datetime object that's `duration` in the future.

        The converter supports the following symbols for each unit of time:
        - years: `Y`, `y`, `year`, `years`
        - months: `m`, `month`, `months`
        - weeks: `w`, `W`, `week`, `weeks`
        - days: `d`, `D`, `day`, `days`
        - hours: `H`, `h`, `hour`, `hours`
        - minutes: `M`, `minute`, `minutes`
        - seconds: `S`, `s`, `second`, `seconds`

        The units need to be provided in descending order of magnitude.
        """
        match = self.duration_parser.fullmatch(duration)
        if not match:
            raise BadArgument(f"`{duration}` is not a valid duration string.")

        duration_dict = {unit: int(amount) for unit, amount in match.groupdict(default=0).items()}
        delta = relativedelta(**duration_dict)
        now = datetime.utcnow()

        return now + delta


class ISODateTime(Converter):
    """Converts an ISO-8601 datetime string into a datetime.datetime."""

    async def convert(self, ctx: Context, datetime_string: str) -> datetime:
        """
        Converts a ISO-8601 `datetime_string` into a `datetime.datetime` object.

        The converter is flexible in the formats it accepts, as it uses the `isoparse` method of
        `dateutil.parser`. In general, it accepts datetime strings that start with a date,
        optionally followed by a time. Specifying a timezone offset in the datetime string is
        supported, but the `datetime` object will be converted to UTC and will be returned without
        `tzinfo` as a timezone-unaware `datetime` object.

        See: https://dateutil.readthedocs.io/en/stable/parser.html#dateutil.parser.isoparse

        Formats that are guaranteed to be valid by our tests are:

        - `YYYY-mm-ddTHH:MM:SSZ` | `YYYY-mm-dd HH:MM:SSZ`
        - `YYYY-mm-ddTHH:MM:SS±HH:MM` | `YYYY-mm-dd HH:MM:SS±HH:MM`
        - `YYYY-mm-ddTHH:MM:SS±HHMM` | `YYYY-mm-dd HH:MM:SS±HHMM`
        - `YYYY-mm-ddTHH:MM:SS±HH` | `YYYY-mm-dd HH:MM:SS±HH`
        - `YYYY-mm-ddTHH:MM:SS` | `YYYY-mm-dd HH:MM:SS`
        - `YYYY-mm-ddTHH:MM` | `YYYY-mm-dd HH:MM`
        - `YYYY-mm-dd`
        - `YYYY-mm`
        - `YYYY`

        Note: ISO-8601 specifies a `T` as the separator between the date and the time part of the
        datetime string. The converter accepts both a `T` and a single space character.
        """
        try:
            dt = dateutil.parser.isoparse(datetime_string)
        except ValueError:
            raise BadArgument(f"`{datetime_string}` is not a valid ISO-8601 datetime string")

        if dt.tzinfo:
            dt = dt.astimezone(dateutil.tz.UTC)
            dt = dt.replace(tzinfo=None)

        return dt


def proxy_user(user_id: str) -> discord.Object:
    """
    Create a proxy user object from the given id.

    Used when a Member or User object cannot be resolved.
    """
    log.trace(f"Attempting to create a proxy user for the user id {user_id}.")

    try:
        user_id = int(user_id)
    except ValueError:
        log.debug(f"Failed to create proxy user {user_id}: could not convert to int.")
        raise BadArgument(f"User ID `{user_id}` is invalid - could not convert to an integer.")

    user = discord.Object(user_id)
    user.mention = user.id
    user.avatar_url_as = lambda static_format: None

    return user


class FetchedUser(Converter):
    """
    Fetches from the Discord API and returns a `discord.User` or `discord.Object` object, given an ID.

    If the fetching is successful, a `discord.User` object is returned. If it fails and
    the error doesn't imply the user doesn't exist, then a `discord.Object` is returned
    via the `user_proxy` function.
    """

    @staticmethod
    async def convert(ctx: Context, user_id: str) -> t.Union[discord.User, discord.Object]:
        """Convert `user_id` to a `discord.User` object, after fetching from the Discord API."""
        try:
            user_id = int(user_id)
            log.trace(f"Fetching user {user_id}...")
            return await ctx.bot.fetch_user(user_id)
        except ValueError:
            log.debug(f"Failed to fetch user {user_id}: could not convert to int.")
            raise BadArgument(f"The provided argument can't be turned into integer: `{user_id}`")
        except discord.HTTPException as e:
            # If the Discord error isn't `Unknown user`, save it in the log and return a proxy instead
            if e.code != 10013:
                log.warning(f"Failed to fetch user, returning a proxy instead: status {e.status}")
                return proxy_user(user_id)

            log.debug(f"Failed to fetch user {user_id}: user does not exist.")
            raise BadArgument(f"User `{user_id}` does not exist")
