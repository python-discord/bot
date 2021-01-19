from async_rediscache import RedisCache

# This dictionary maps a help channel to the time it was claimed
# RedisCache[discord.TextChannel.id, UtcPosixTimestamp]
claim_times = RedisCache(namespace="HelpChannels.claim_times")

# This cache tracks which channels are claimed by which members.
# RedisCache[discord.TextChannel.id, t.Union[discord.User.id, discord.Member.id]]
claimants = RedisCache(namespace="HelpChannels.help_channel_claimants")

# This cache maps a help channel to original question message in same channel.
# RedisCache[discord.TextChannel.id, discord.Message.id]
question_messages = RedisCache(namespace="HelpChannels.question_messages")

# This cache maps a help channel to whether it has had any
# activity other than the original claimant. True being no other
# activity and False being other activity.
# RedisCache[discord.TextChannel.id, bool]
unanswered = RedisCache(namespace="HelpChannels.unanswered")
