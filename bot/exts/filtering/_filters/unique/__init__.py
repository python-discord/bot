from os.path import dirname

from bot.exts.filtering._filters.filter import UniqueFilter
from bot.exts.filtering._utils import subclasses_in_package

unique_filter_types = subclasses_in_package(dirname(__file__), f"{__name__}.", UniqueFilter)
unique_filter_types = {filter_.name: filter_ for filter_ in unique_filter_types}

__all__ = [unique_filter_types]
