from os.path import dirname

from bot.exts.filtering._filter_lists.filter_list import FilterList, ListType, ListTypeConverter
from bot.exts.filtering._utils import subclasses_in_package

filter_list_types = subclasses_in_package(dirname(__file__), f"{__name__}.", FilterList)
filter_list_types = {filter_list.name: filter_list for filter_list in filter_list_types}

__all__ = [filter_list_types, FilterList, ListType, ListTypeConverter]
