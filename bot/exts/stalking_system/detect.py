import discord
import bot

# Assumes a `channel_word_trackers` dictionary is defined elsewhere

@bot.event
async def on_message(message: discord.Message):
    # Ignore bot messages
    if message.author.bot:
        return

    # Check if this channel has any tracked words
    channel_id = message.channel.id
    if channel_id not in channel_word_trackers:
        return

    # Get the words tracked for this channel
    tracked_words_for_channel = channel_word_trackers[channel_id]
    content_lower = message.content.lower()
    
    # Check each tracked word in this channel
    for word, user_ids in tracked_words_for_channel.items():
        if word in content_lower:
            if is_spam(message):
                continue
            else:
                # If not spam, DM all users who track this word in this channel
                for user_id in user_ids:
                    user = bot.get_user(user_id)
                    if user:
                        await send_dm(
                            user,
                            f"A tracked word ('{word}') was mentioned by {message.author.mention} in {message.channel.mention}."
                        )
