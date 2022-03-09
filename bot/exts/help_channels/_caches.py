from async_rediscache import RedisCache

# This dictionary maps a help channel to the time it was claimed
# RedisCache[disnake.TextChannel.id, UtcPosixTimestamp]
claim_times = RedisCache(namespace="HelpChannels.claim_times")

# This cache tracks which channels are claimed by which members.
# RedisCache[disnake.TextChannel.id, t.Union[disnake.User.id, disnake.Member.id]]
claimants = RedisCache(namespace="HelpChannels.help_channel_claimants")

# Stores the timestamp of the last message from the claimant of a help channel
# RedisCache[disnake.TextChannel.id, UtcPosixTimestamp]
claimant_last_message_times = RedisCache(namespace="HelpChannels.claimant_last_message_times")

# This cache maps a help channel to the timestamp of the last non-claimant message.
# This cache being empty for a given help channel indicates the question is unanswered.
# RedisCache[disnake.TextChannel.id, UtcPosixTimestamp]
non_claimant_last_message_times = RedisCache(namespace="HelpChannels.non_claimant_last_message_times")

# This cache maps a help channel to original question message in same channel.
# RedisCache[disnake.TextChannel.id, disnake.Message.id]
question_messages = RedisCache(namespace="HelpChannels.question_messages")

# This cache keeps track of the dynamic message ID for
# the continuously updated message in the #How-to-get-help channel.
dynamic_message = RedisCache(namespace="HelpChannels.dynamic_message")

# This cache keeps track of who has help-dms on.
# RedisCache[disnake.User.id, bool]
help_dm = RedisCache(namespace="HelpChannels.help_dm")

# This cache tracks member who are participating and opted in to help channel dms.
# serialise the set as a comma separated string to allow usage with redis
# RedisCache[disnake.TextChannel.id, str[set[disnake.User.id]]]
session_participants = RedisCache(namespace="HelpChannels.session_participants")
