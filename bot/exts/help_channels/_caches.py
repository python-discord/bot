from async_rediscache import RedisCache

# This dictionary maps a help channel to the time it was claimed
# RedisCache[discord.TextChannel.id, UtcPosixTimestamp]
claim_times = RedisCache(namespace="HelpChannels.claim_times")

# This cache tracks which channels are claimed by which members.
# RedisCache[discord.TextChannel.id, t.Union[discord.User.id, discord.Member.id]]
claimants = RedisCache(namespace="HelpChannels.help_channel_claimants")

# Stores the timestamp of the last message from the claimant of a help channel
# RedisCache[discord.TextChannel.id, UtcPosixTimestamp]
claimant_last_message_times = RedisCache(namespace="HelpChannels.claimant_last_message_times")

# This cache maps a help channel to the timestamp of the last non-claimant message.
# This cache being empty for a given help channel indicates the question is unanswered.
# RedisCache[discord.TextChannel.id, UtcPosixTimestamp]
non_claimant_last_message_times = RedisCache(namespace="HelpChannels.non_claimant_last_message_times")

# This cache maps a help channel to original question message in same channel.
# RedisCache[discord.TextChannel.id, discord.Message.id]
question_messages = RedisCache(namespace="HelpChannels.question_messages")
