import logging
import typing as t
from datetime import datetime

from bot.constants import Colours
from bot.exts.backend.branding._constants import Month
from bot.exts.backend.branding._errors import BrandingError

log = logging.getLogger(__name__)


class SeasonBase:
    """
    Base for Seasonal classes.

    This serves as the off-season fallback for when no specific
    seasons are active.

    Seasons are 'registered' simply by inheriting from `SeasonBase`.
    We discover them by calling `__subclasses__`.
    """

    season_name: str = "Evergreen"

    colour: str = Colours.soft_green
    description: str = "The default season!"

    branding_path: str = "seasonal/evergreen"

    months: t.Set[Month] = set(Month)


class Christmas(SeasonBase):
    """Branding for December."""

    season_name = "Festive season"

    colour = Colours.soft_red
    description = (
        "The time is here to get into the festive spirit! No matter who you are, where you are, "
        "or what beliefs you may follow, we hope every one of you enjoy this festive season!"
    )

    branding_path = "seasonal/christmas"

    months = {Month.DECEMBER}


class Easter(SeasonBase):
    """Branding for April."""

    season_name = "Easter"

    colour = Colours.bright_green
    description = (
        "Bunny here, bunny there, bunny everywhere! Here at Python Discord, we celebrate "
        "our version of Easter during the entire month of April."
    )

    branding_path = "seasonal/easter"

    months = {Month.APRIL}


class Halloween(SeasonBase):
    """Branding for October."""

    season_name = "Halloween"

    colour = Colours.orange
    description = "Trick or treat?!"

    branding_path = "seasonal/halloween"

    months = {Month.OCTOBER}


class Pride(SeasonBase):
    """Branding for June."""

    season_name = "Pride"

    colour = Colours.pink
    description = (
        "The month of June is a special month for us at Python Discord. It is very important to us "
        "that everyone feels welcome here, no matter their origin, identity or sexuality. During the "
        "month of June, while some of you are participating in Pride festivals across the world, "
        "we will be celebrating individuality and commemorating the history and challenges "
        "of the LGBTQ+ community with a Pride event of our own!"
    )

    branding_path = "seasonal/pride"

    months = {Month.JUNE}


class Valentines(SeasonBase):
    """Branding for February."""

    season_name = "Valentines"

    colour = Colours.pink
    description = "Love is in the air!"

    branding_path = "seasonal/valentines"

    months = {Month.FEBRUARY}


class Wildcard(SeasonBase):
    """Branding for August."""

    season_name = "Wildcard"

    colour = Colours.purple
    description = "A season full of surprises!"

    months = {Month.AUGUST}


def get_all_seasons() -> t.List[t.Type[SeasonBase]]:
    """Give all available season classes."""
    return [SeasonBase] + SeasonBase.__subclasses__()


def get_current_season() -> t.Type[SeasonBase]:
    """Give active season, based on current UTC month."""
    current_month = Month(datetime.utcnow().month)

    active_seasons = tuple(
        season
        for season in SeasonBase.__subclasses__()
        if current_month in season.months
    )

    if not active_seasons:
        return SeasonBase

    return active_seasons[0]


def get_season(name: str) -> t.Optional[t.Type[SeasonBase]]:
    """
    Give season such that its class name or its `season_name` attr match `name` (caseless).

    If no such season exists, return None.
    """
    name = name.casefold()

    for season in get_all_seasons():
        matches = (season.__name__.casefold(), season.season_name.casefold())

        if name in matches:
            return season


def _validate_season_overlap() -> None:
    """
    Raise BrandingError if there are any colliding seasons.

    This serves as a local test to ensure that seasons haven't been misconfigured.
    """
    month_to_season = {}

    for season in SeasonBase.__subclasses__():
        for month in season.months:
            colliding_season = month_to_season.get(month)

            if colliding_season:
                raise BrandingError(f"Season {season} collides with {colliding_season} in {month.name}")
            else:
                month_to_season[month] = season


_validate_season_overlap()
