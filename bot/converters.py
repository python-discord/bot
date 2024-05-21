from __future__ import annotations

import re
import typing as t
from datetime import UTC, datetime
from ssl import CertificateError

import dateutil.parser
import discord
from aiohttp import ClientConnectorError
from dateutil.relativedelta import relativedelta
from discord.ext.commands import BadArgument, Context, Converter, IDConverter, MemberConverter, UserConverter
from discord.utils import snowflake_time
from pydis_core.site_api import ResponseCodeError
from pydis_core.utils import unqualify
from pydis_core.utils.regex import DISCORD_INVITE

from bot import exts, instance as bot_instance
from bot.constants import URLs
from bot.errors import InvalidInfractionError
from bot.exts.info.doc import _inventory_parser
from bot.log import get_logger
from bot.utils import time

if t.TYPE_CHECKING:
    from bot.exts.info.source import SourceType

log = get_logger(__name__)

DISCORD_EPOCH_DT = snowflake_time(0)
RE_USER_MENTION = re.compile(r"<@!?([0-9]+)>$")


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
        invite_code = DISCORD_INVITE.match(server_invite)
        if invite_code:
            response = await ctx.bot.http_session.get(
                f"{URLs.discord_invite_api}/{invite_code.group('invite')}"
            )
            if response.status != 404:
                invite_data = await response.json()
                return invite_data.get("guild")

        id_converter = IDConverter()
        if id_converter._get_id_match(server_invite):
            raise BadArgument("Guild IDs are not supported, only invites.")

        raise BadArgument("This does not appear to be a valid Discord server invite.")


class Extension(Converter):
    """
    Fully qualify the name of an extension and ensure it exists.

    The * and ** values bypass this when used with the reload command.
    """

    async def convert(self, ctx: Context, argument: str) -> str:
        """Fully qualify the name of an extension and ensure it exists."""
        # Special values to reload all extensions
        if argument == "*" or argument == "**":
            return argument

        argument = argument.lower()

        if argument in bot_instance.all_extensions:
            return argument

        if (qualified_arg := f"{exts.__name__}.{argument}") in bot_instance.all_extensions:
            return qualified_arg

        matches = []
        for ext in bot_instance.all_extensions:
            if argument == unqualify(ext):
                matches.append(ext)

        if len(matches) > 1:
            matches.sort()
            names = "\n".join(matches)
            raise BadArgument(
                f":x: `{argument}` is an ambiguous extension name. "
                f"Please use one of the following fully-qualified names.```\n{names}```"
            )

        if matches:
            return matches[0]
        raise BadArgument(f":x: Could not find the extension `{argument}`.")


class PackageName(Converter):
    """
    A converter that checks whether the given string is a valid package name.

    Package names are used for stats and are restricted to the a-z and _ characters.
    """

    PACKAGE_NAME_RE = re.compile(r"[^a-z0-9_]")

    @classmethod
    async def convert(cls, ctx: Context, argument: str) -> str:
        """Checks whether the given string is a valid package name."""
        if cls.PACKAGE_NAME_RE.search(argument):
            raise BadArgument("The provided package name is not valid; please only use the _, 0-9, and a-z characters.")
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
            if url.startswith("https"):
                raise BadArgument(
                    f"Got a `CertificateError` for URL `{url}`. Does it support HTTPS?"
                )
            raise BadArgument(f"Got a `CertificateError` for URL `{url}`.")
        except ValueError:
            raise BadArgument(f"`{url}` doesn't look like a valid hostname to me.")
        except ClientConnectorError:
            raise BadArgument(f"Cannot connect to host with URL `{url}`.")
        return url


class Inventory(Converter):
    """
    Represents an Intersphinx inventory URL.

    This converter checks whether intersphinx accepts the given inventory URL, and raises
    `BadArgument` if that is not the case or if the url is unreachable.

    Otherwise, it returns the url and the fetched inventory dict in a tuple.
    """

    @staticmethod
    async def convert(ctx: Context, url: str) -> tuple[str, _inventory_parser.InventoryDict]:
        """Convert url to Intersphinx inventory URL."""
        await ctx.typing()
        try:
            inventory = await _inventory_parser.fetch_inventory(url)
        except _inventory_parser.InvalidHeaderError:
            raise BadArgument("Unable to parse inventory because of invalid header, check if URL is correct.")
        else:
            if inventory is None:
                raise BadArgument(
                    f"Failed to fetch inventory file after {_inventory_parser.FAILED_REQUEST_ATTEMPTS} attempts."
                )
            return url, inventory


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
        if (datetime.now(UTC) - time).days < -1:
            raise BadArgument(f"{error}: timestamp is too far into the future.")

        return snowflake


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
        if not (delta := time.parse_duration_string(duration)):
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
        now = datetime.now(UTC)

        try:
            return now + delta
        except (ValueError, OverflowError):
            raise BadArgument(f"`{duration}` results in a datetime outside the supported range.")


class Age(DurationDelta):
    """Convert duration strings into UTC datetime.datetime objects."""

    async def convert(self, ctx: Context, duration: str) -> datetime:
        """
        Converts a `duration` string to a datetime object that's `duration` in the past.

        The converter supports the same symbols for each unit of time as its parent class.
        """
        delta = await super().convert(ctx, duration)
        now = datetime.now(UTC)

        try:
            return now - delta
        except (ValueError, OverflowError):
            raise BadArgument(f"`{duration}` results in a datetime outside the supported range.")


class OffTopicName(Converter):
    """A converter that ensures an added off-topic name is valid."""

    ALLOWED_CHARACTERS = r"ABCDEFGHIJKLMNOPQRSTUVWXYZ!?'`-<>\/"
    TRANSLATED_CHARACTERS = "𝖠𝖡𝖢𝖣𝖤𝖥𝖦𝖧𝖨𝖩𝖪𝖫𝖬𝖭𝖮𝖯𝖰𝖱𝖲𝖳𝖴𝖵𝖶𝖷𝖸𝖹ǃ？’’-＜＞⧹⧸"  # noqa: RUF001

    @classmethod
    def translate_name(cls, name: str, *, from_unicode: bool = True) -> str:
        """
        Translates `name` into a format that is allowed in discord channel names.

        If `from_unicode` is True, the name is translated from a discord-safe format, back to normalized text.
        """
        if from_unicode:
            table = str.maketrans(cls.ALLOWED_CHARACTERS, cls.TRANSLATED_CHARACTERS)
        else:
            table = str.maketrans(cls.TRANSLATED_CHARACTERS, cls.ALLOWED_CHARACTERS)

        return name.translate(table)

    async def convert(self, ctx: Context, argument: str) -> str:
        """Attempt to replace any invalid characters with their approximate Unicode equivalent."""
        # Chain multiple words to a single one
        argument = "-".join(argument.split())

        if not (2 <= len(argument) <= 96):
            raise BadArgument("Channel name must be between 2 and 96 chars long")

        if not all(c.isalnum() or c in self.ALLOWED_CHARACTERS for c in argument):
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
        supported, but the `datetime` object will be converted to UTC. If no timezone is specified, the datetime will
        be assumed to be in UTC already. In all cases, the returned object will have the UTC timezone.

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
            dt = dt.astimezone(UTC)
        else:  # Without a timezone, assume it represents UTC.
            dt = dt.replace(tzinfo=UTC)

        return dt


class HushDurationConverter(Converter):
    """Convert passed duration to `int` minutes or `None`."""

    MINUTES_RE = re.compile(r"(\d+)(?:M|m|$)")

    async def convert(self, ctx: Context, argument: str) -> int:
        """
        Convert `argument` to a duration that's max 15 minutes or None.

        If `"forever"` is passed, -1 is returned; otherwise an int of the extracted time.
        Accepted formats are:
        * <duration>,
        * <duration>m,
        * <duration>M,
        * forever.
        """
        if argument == "forever":
            return -1
        match = self.MINUTES_RE.match(argument)
        if not match:
            raise BadArgument(f"{argument} is not a valid minutes duration.")

        duration = int(match.group(1))
        if duration > 15:
            raise BadArgument("Duration must be at most 15 minutes.")
        return duration


def _is_an_unambiguous_user_argument(argument: str) -> bool:
    """Check if the provided argument is a user mention or user id."""
    user_id = IDConverter._get_id_match(argument)
    user_mention = RE_USER_MENTION.match(argument)

    return bool(user_id or user_mention)


AMBIGUOUS_ARGUMENT_MSG = "`{argument}` is not a User mention or a User ID."


class UnambiguousUser(UserConverter):
    """
    Converts to a `discord.User`, but only if a mention or userID is provided.

    Unlike the default `UserConverter`, it doesn't allow conversion from a name.
    This is useful in cases where that lookup strategy would lead to too much ambiguity.
    """

    async def convert(self, ctx: Context, argument: str) -> discord.User:
        """Convert the `argument` to a `discord.User`."""
        if _is_an_unambiguous_user_argument(argument):
            return await super().convert(ctx, argument)
        raise BadArgument(AMBIGUOUS_ARGUMENT_MSG.format(argument=argument))


class UnambiguousMember(MemberConverter):
    """
    Converts to a `discord.Member`, but only if a mention or userID is provided.

    Unlike the default `MemberConverter`, it doesn't allow conversion from a name or nickname.
    This is useful in cases where that lookup strategy would lead to too much ambiguity.
    """

    async def convert(self, ctx: Context, argument: str) -> discord.Member:
        """Convert the `argument` to a `discord.Member`."""
        if _is_an_unambiguous_user_argument(argument):
            return await super().convert(ctx, argument)
        raise BadArgument(AMBIGUOUS_ARGUMENT_MSG.format(argument=argument))


class Infraction(Converter):
    """
    Attempts to convert a given infraction ID into an infraction.

    Alternatively, `l`, `last`, or `recent` can be passed in order to
    obtain the most recent infraction by the actor.
    """

    async def convert(self, ctx: Context, arg: str) -> dict | None:
        """Attempts to convert `arg` into an infraction `dict`."""
        if arg in ("l", "last", "recent"):
            params = {
                "actor__id": ctx.author.id,
                "ordering": "-inserted_at"
            }

            infractions = await ctx.bot.api_client.get("bot/infractions/expanded", params=params)

            if not infractions:
                raise BadArgument(
                    "Couldn't find most recent infraction; you have never given an infraction."
                )
            return infractions[0]

        try:
            return await ctx.bot.api_client.get(f"bot/infractions/{arg}/expanded")
        except ResponseCodeError as e:
            if e.status == 404:
                raise InvalidInfractionError(
                    converter=Infraction,
                    original=e,
                    infraction_arg=arg
                )
            raise e


if t.TYPE_CHECKING:
    ValidDiscordServerInvite = dict
    ValidFilterListType = str
    Extension = str
    PackageName = str
    ValidURL = str
    Inventory = tuple[str, _inventory_parser.InventoryDict]
    Snowflake = int
    SourceConverter = SourceType
    DurationDelta = relativedelta
    Duration = datetime
    Age = datetime
    OffTopicName = str
    ISODateTime = datetime
    HushDurationConverter = int
    UnambiguousUser = discord.User
    UnambiguousMember = discord.Member
    Infraction = dict | None

Expiry = Duration | ISODateTime
DurationOrExpiry = DurationDelta | ISODateTime
MemberOrUser = discord.Member | discord.User
UnambiguousMemberOrUser = UnambiguousMember | UnambiguousUser
