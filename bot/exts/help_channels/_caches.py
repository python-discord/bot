from async_rediscache import RedisCache

# Stores posts that have had a non-claimant, non-bot, reply.
# Currently only used to determine whether the post was answered or not when collecting stats.
posts_with_non_claimant_messages = RedisCache(namespace="HelpChannels.posts_with_non_claimant_messages")
