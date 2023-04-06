# Filters Development
This file gives a short overview of the extension, and shows how to perform some basic changes/additions to it.

## Overview
The main idea is that there is a list of filters each deciding whether they apply to the given content.
For example, there can be a filter that decides it will trigger when the content contains the string "lemon".

There are several types of filters, and two filters of the same type differ by their content.
For example, filters of type "token" search for a specific token inside the provided string.
One token filter might look for the string "lemon", while another will look for the string "joe".

Each filter has a set of settings that decide when it triggers (e.g. in which channels, in which categories, etc.), and what happens if it does (e.g. delete the message, ping specific roles/users, etc.).
Filters of a specific type can have additional settings that are special to them.

A list of filters is contained within a filter list.
The filter list gets content to filter, and dispatches it to each of its filters.
It takes the answers from its filters and returns a unified response (e.g. if at least one of the filters says it should be deleted, then the filter list response will include it).

A filter list has the same set of possible settings, which act as defaults.
If a filter in the list doesn't define a value for a setting (meaning it has a value of None), it will use the value of the containing filter list.

The cog receives "filtering events". For example, a new message is sent.
It creates a "filtering context" with everything a filtering list needs to know to provide an answer for what should be done.
For example, if the event is a new message, then the content to filter is the content of the message, embeds if any exist, etc.

The cog dispatches the event to each filter list, gets the result from each, compiles them, and takes any action dictated by them.
For example, if any of the filter lists want the message to be deleted, then the cog will delete it.

## Example Changes
### Creating a new type of filter list
1. Head over to `bot.exts.filtering._filter_lists` and create a new Python file.
2. Subclass the FilterList class in `bot.exts.filtering._filter_lists.filter_list` and implement its abstract methods. Make sure to set the `name` class attribute.

You can now add filter lists to the database with the same name defined in the new FilterList subclass.

### Creating a new type of filter
1. Head over to `bot.exts.filtering._filters` and create a new Python file.
2. Subclass the Filter class in `bot.exts.filtering._filters.filter` and implement its abstract methods.
3. Make sure to set the `name` class attribute, and have one of the FilterList subclasses return this new Filter subclass in `get_filter_type`.

### Creating a new type of setting
1. Head over to `bot.exts.filtering._settings_types`, and open a new Python file in either `actions` or `validations`, depending on whether you want to subclass `ActionEntry` or `ValidationEntry`.
2. Subclass one of the aforementioned classes, and implement its abstract methods. Make sure to set the `name` and `description` class attributes.

You can now make the appropriate changes to the site repo:
1. Add a new field in the `Filter` and `FilterList` models. Make sure that on `Filter` it's nullable, and on `FilterList` it isn't.
2. In `serializers.py`, add the new field to `SETTINGS_FIELDS`, and to `ALLOW_BLANK_SETTINGS` or `ALLOW_EMPTY_SETTINGS` if appropriate. If it's not a part of any group of settings, add it `BASE_SETTINGS_FIELDS`, otherwise add it to the appropriate group or create a new one.
3. If you created a new group, make sure it's used in `to_representation`.
4. Update the docs in the filter viewsets.

You can merge the changes to the bot first - if no such field is loaded from the database it'll just be ignored.

You can define entries that are a group of fields in the database.
In that case the created subclass should have fields whose names are the names of the fields in the database.
Then, the description will be a dictionary, whose keys are the names of the fields, and values are the descriptions for each field.

### Creating a new type of filtering event
1. Head over to `bot.exts.filtering._filter_context` and add a new value to the `Event` enum.
2. Implement the dispatching and actioning of the new event in the cog, by either adding it to an existing even listener, or creating a new one.
3. Have the appropriate filter lists subscribe to the event, so they receive it.
4. Have the appropriate unique filters (currently under `unique` and `antispam` in `bot.exts.filtering._filters`) subscribe to the event, so they receive it.

It should be noted that the filtering events don't need to correspond to Discord events. For example, `nickname` isn't a Discord event and is dispatched when a message is sent.
