import logging
import re
import typing as t
from datetime import datetime
from functools import partial
from ssl import CertificateError

import dateutil.parser
import dateutil.tz
import discord
from aiohttp import ClientConnectorError
from dateutil.relativedelta import relativedelta
from discord.ext.commands import BadArgument, Bot, Context, Converter, IDConverter, UserConverter
from discord.utils import DISCORD_EPOCH, snowflake_time

from bot.api import ResponseCodeError
from bot.constants import URLs
from bot.utils.regex import INVITE_RE
from bot.utils.time import parse_duration_string

log = logging.getLogger(__name__)

DISCORD_EPOCH_DT = datetime.utcfromtimestamp(DISCORD_EPOCH / 1000)
RE_USER_MENTION = re.compile(r"<@!?([0-9]+)>$")


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


class ValidDiscordServerInvite(Converter):
    """
    A converter that validates whether a given string is a valid Discord server invite.

    Raises 'BadArgument' if:
    - The string is not a valid Discord server invite.
    - The string is valid, but is an invite for a group DM.
    - The string is valid, but is expired.

    Returns a (partial) guild object if:
    - The string is a valid vanity
    - The string is a full invite URI
    - The string contains the invite code (the stuff after discord.gg/)

    See the Discord API docs for documentation on the guild object:
    https://discord.com/developers/docs/resources/guild#guild-object
    """

    async def convert(self, ctx: Context, server_invite: str) -> dict:
        """Check whether the string is a valid Discord server invite."""
        invite_code = INVITE_RE.search(server_invite)
        if invite_code:
            response = await ctx.bot.http_session.get(
                f"{URLs.discord_invite_api}/{invite_code[1]}"
            )
            if response.status != 404:
                invite_data = await response.json()
                return invite_data.get("guild")

        id_converter = IDConverter()
        if id_converter._get_id_match(server_invite):
            raise BadArgument("Guild IDs are not supported, only invites.")

        raise BadArgument("This does not appear to be a valid Discord server invite.")


class ValidFilterListType(Converter):
    """
    A converter that checks whether the given string is a valid FilterList type.

    Raises `BadArgument` if the argument is not a valid FilterList type, and simply
    passes through the given argument otherwise.
    """

    @staticmethod
    async def get_valid_types(bot: Bot) -> list:
        """
        Try to get a list of valid filter list types.

        Raise a BadArgument if the API can't respond.
        """
        try:
            valid_types = await bot.api_client.get('bot/filter-lists/get-types')
        except ResponseCodeError:
            raise BadArgument("Cannot validate list_type: Unable to fetch valid types from API.")

        return [enum for enum, classname in valid_types]

    async def convert(self, ctx: Context, list_type: str) -> str:
        """Checks whether the given string is a valid FilterList type."""
        valid_types = await self.get_valid_types(ctx.bot)
        list_type = list_type.upper()

        if list_type not in valid_types:

            # Maybe the user is using the plural form of this type,
            # e.g. "guild_invites" instead of "guild_invite".
            #
            # This code will support the simple plural form (a single 's' at the end),
            # which works for all current list types, but if a list type is added in the future
            # which has an irregular plural form (like 'ies'), this code will need to be
            # refactored to support this.
            if list_type.endswith("S") and list_type[:-1] in valid_types:
                list_type = list_type[:-1]

            else:
                valid_types_list = '\n'.join([f"• {type_.lower()}" for type_ in valid_types])
                raise BadArgument(
                    f"You have provided an invalid list type!\n\n"
                    f"Please provide one of the following: \n{valid_types_list}"
                )
        return list_type


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


class Snowflake(IDConverter):
    """
    Converts to an int if the argument is a valid Discord snowflake.

    A snowflake is valid if:

    * It consists of 15-21 digits (0-9)
    * Its parsed datetime is after the Discord epoch
    * Its parsed datetime is less than 1 day after the current time
    """

    async def convert(self, ctx: Context, arg: str) -> int:
        """
        Ensure `arg` matches the ID pattern and its timestamp is in range.

        Return `arg` as an int if it's a valid snowflake.
        """
        error = f"Invalid snowflake {arg!r}"

        if not self._get_id_match(arg):
            raise BadArgument(error)

        snowflake = int(arg)

        try:
            time = snowflake_time(snowflake)
        except (OverflowError, OSError) as e:
            # Not sure if this can ever even happen, but let's be safe.
            raise BadArgument(f"{error}: {e}")

        if time < DISCORD_EPOCH_DT:
            raise BadArgument(f"{error}: timestamp is before the Discord epoch.")
        elif (datetime.utcnow() - time).days < -1:
            raise BadArgument(f"{error}: timestamp is too far into the future.")

        return snowflake


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
        tag_name = tag_name.lower().strip()

        # The tag name has at least one invalid character.
        if ascii(tag_name)[1:-1] != tag_name:
            raise BadArgument("Don't be ridiculous, you can't use that character!")

        # The tag name is either empty, or consists of nothing but whitespace.
        elif not tag_name:
            raise BadArgument("Tag names should not be empty, or filled with whitespace.")

        # The tag name is longer than 127 characters.
        elif len(tag_name) > 127:
            raise BadArgument("Are you insane? That's way too long!")

        # The tag name is ascii but does not contain any letters.
        elif not any(character.isalpha() for character in tag_name):
            raise BadArgument("Tag names must contain at least one letter.")

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
            raise BadArgument("Tag contents should not be empty, or filled with whitespace.")

        return tag_content


class DurationDelta(Converter):
    """Convert duration strings into dateutil.relativedelta.relativedelta objects."""

    async def convert(self, ctx: Context, duration: str) -> relativedelta:
        """
        Converts a `duration` string to a relativedelta object.

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
        if not (delta := parse_duration_string(duration)):
            raise BadArgument(f"`{duration}` is not a valid duration string.")

        return delta


class Duration(DurationDelta):
    """Convert duration strings into UTC datetime.datetime objects."""

    async def convert(self, ctx: Context, duration: str) -> datetime:
        """
        Converts a `duration` string to a datetime object that's `duration` in the future.

        The converter supports the same symbols for each unit of time as its parent class.
        """
        delta = await super().convert(ctx, duration)
        now = datetime.utcnow()

        try:
            return now + delta
        except (ValueError, OverflowError):
            raise BadArgument(f"`{duration}` results in a datetime outside the supported range.")


class OffTopicName(Converter):
    """A converter that ensures an added off-topic name is valid."""

    ALLOWED_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ!?'`-"

    @classmethod
    def translate_name(cls, name: str, *, from_unicode: bool = True) -> str:
        """
        Translates `name` into a format that is allowed in discord channel names.

        If `from_unicode` is True, the name is translated from a discord-safe format, back to normalized text.
        """
        if from_unicode:
            table = str.maketrans(cls.ALLOWED_CHARACTERS, '𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹ǃ？’’-')
        else:
            table = str.maketrans('𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹ǃ？’’-', cls.ALLOWED_CHARACTERS)

        return name.translate(table)

    async def convert(self, ctx: Context, argument: str) -> str:
        """Attempt to replace any invalid characters with their approximate Unicode equivalent."""
        # Chain multiple words to a single one
        argument = "-".join(argument.split())

        if not (2 <= len(argument) <= 96):
            raise BadArgument("Channel name must be between 2 and 96 chars long")

        elif not all(c.isalnum() or c in self.ALLOWED_CHARACTERS for c in argument):
            raise BadArgument(
                "Channel name must only consist of "
                "alphanumeric characters, minus signs or apostrophes."
            )

        # Replace invalid characters with unicode alternatives.
        return self.translate_name(argument)


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


class HushDurationConverter(Converter):
    """Convert passed duration to `int` minutes or `None`."""

    MINUTES_RE = re.compile(r"(\d+)(?:M|m|$)")

    async def convert(self, ctx: Context, argument: str) -> t.Optional[int]:
        """
        Convert `argument` to a duration that's max 15 minutes or None.

        If `"forever"` is passed, None is returned; otherwise an int of the extracted time.
        Accepted formats are:
        * <duration>,
        * <duration>m,
        * <duration>M,
        * forever.
        """
        if argument == "forever":
            return None
        match = self.MINUTES_RE.match(argument)
        if not match:
            raise BadArgument(f"{argument} is not a valid minutes duration.")

        duration = int(match.group(1))
        if duration > 15:
            raise BadArgument("Duration must be at most 15 minutes.")
        return duration


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
    user.display_name = f"<@{user.id}>"
    user.avatar_url_as = lambda static_format: None
    user.bot = False

    return user


class UserMentionOrID(UserConverter):
    """
    Converts to a `discord.User`, but only if a mention or userID is provided.

    Unlike the default `UserConverter`, it doesn't allow conversion from a name or name#descrim.
    This is useful in cases where that lookup strategy would lead to ambiguity.
    """

    async def convert(self, ctx: Context, argument: str) -> discord.User:
        """Convert the `arg` to a `discord.User`."""
        match = self._get_id_match(argument) or RE_USER_MENTION.match(argument)

        if match is not None:
            return await super().convert(ctx, argument)
        else:
            raise BadArgument(f"`{argument}` is not a User mention or a User ID.")


class FetchedUser(UserConverter):
    """
    Converts to a `discord.User` or, if it fails, a `discord.Object`.

    Unlike the default `UserConverter`, which only does lookups via the global user cache, this
    converter attempts to fetch the user via an API call to Discord when the using the cache is
    unsuccessful.

    If the fetch also fails and the error doesn't imply the user doesn't exist, then a
    `discord.Object` is returned via the `user_proxy` converter.

    The lookup strategy is as follows (in order):

    1. Lookup by ID.
    2. Lookup by mention.
    3. Lookup by name#discrim
    4. Lookup by name
    5. Lookup via API
    6. Create a proxy user with discord.Object
    """

    async def convert(self, ctx: Context, arg: str) -> t.Union[discord.User, discord.Object]:
        """Convert the `arg` to a `discord.User` or `discord.Object`."""
        try:
            return await super().convert(ctx, arg)
        except BadArgument:
            pass

        try:
            user_id = int(arg)
            log.trace(f"Fetching user {user_id}...")
            return await ctx.bot.fetch_user(user_id)
        except ValueError:
            log.debug(f"Failed to fetch user {arg}: could not convert to int.")
            raise BadArgument(f"The provided argument can't be turned into integer: `{arg}`")
        except discord.HTTPException as e:
            # If the Discord error isn't `Unknown user`, return a proxy instead
            if e.code != 10013:
                log.info(f"Failed to fetch user, returning a proxy instead: status {e.status}")
                return proxy_user(arg)

            log.debug(f"Failed to fetch user {arg}: user does not exist.")
            raise BadArgument(f"User `{arg}` does not exist")


def _snowflake_from_regex(pattern: t.Pattern, arg: str) -> int:
    """
    Extract the snowflake from `arg` using a regex `pattern` and return it as an int.

    The snowflake is expected to be within the first capture group in `pattern`.
    """
    match = pattern.match(arg)
    if not match:
        raise BadArgument(f"Mention {str!r} is invalid.")

    return int(match.group(1))


class Infraction(Converter):
    """
    Attempts to convert a given infraction ID into an infraction.

    Alternatively, `l`, `last`, or `recent` can be passed in order to
    obtain the most recent infraction by the actor.
    """

    async def convert(self, ctx: Context, arg: str) -> t.Optional[dict]:
        """Attempts to convert `arg` into an infraction `dict`."""
        if arg in ("l", "last", "recent"):
            params = {
                "actor__id": ctx.author.id,
                "ordering": "-inserted_at"
            }

            infractions = await ctx.bot.api_client.get("bot/infractions", params=params)

            if not infractions:
                raise BadArgument(
                    "Couldn't find most recent infraction; you have never given an infraction."
                )
            else:
                return infractions[0]

        else:
            return await ctx.bot.api_client.get(f"bot/infractions/{arg}")


Expiry = t.Union[Duration, ISODateTime]
FetchedMember = t.Union[discord.Member, FetchedUser]
UserMention = partial(_snowflake_from_regex, RE_USER_MENTION)
