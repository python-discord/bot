from async_rediscache import RedisCache

# This cache keeps track of who has help-dms on.
# RedisCache[discord.User.id, bool]
help_dm = RedisCache(namespace="HelpChannels.help_dm")

# This cache tracks member who are participating and opted in to help channel dms.
# serialise the set as a comma separated string to allow usage with redis
# RedisCache[discord.TextChannel.id, str[set[discord.User.id]]]
session_participants = RedisCache(namespace="HelpChannels.session_participants")

# Stores posts that have had a non-claimant, non-bot, reply.
# Currently only used to determine whether the post was answered or not when collecting stats.
posts_with_non_claimant_messages = RedisCache(namespace="HelpChannels.posts_with_non_claimant_messages")
