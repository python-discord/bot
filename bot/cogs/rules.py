import re
from typing import Optional

from discord import Colour, Embed
from discord.ext.commands import Bot, Context, command

from bot.constants import Channels, STAFF_ROLES
from bot.decorators import redirect_output
from bot.pagination import LinePaginator


class Rules:

    def __init__(self, bot: Bot):
        self.bot = bot

        # We'll get the rules from the API when the
        # site has been updated to the Django Framework.
        # Hard-code the rules for now until the new RulesView is released.

        self.rules = (
            "Be polite, and do not spam.",

            "Follow the [Discord Community Guidelines](https://discordapp.com/guidelines).",

            "Don't intentionally make other people uncomfortable - if someone asks you to stop "
            "discussing something, you should stop.",

            "Be patient both with users asking questions, and the users answering them.",

            "We will not help you with anything that might break a law or the terms of service "
            "of any other community, site, service, or otherwise - No piracy, brute-forcing, "
            "captcha circumvention, sneaker bots, or anything else of that nature.",

            "Listen to and respect the staff members - we're here to help, but we're all human "
            "beings.",

            "All discussion should be kept within the relevant channels for the subject - See the "
            "[channels page](https://pythondiscord.com/about/channels) for more information.",

            "This is an English-speaking server, so please speak English to the best of your "
            "ability - [Google Translate](https://translate.google.com/) should be fine if you're "
            "not sure.",

            "Keep all discussions safe for work - No gore, nudity, sexual soliciting, references "
            "to suicide, or anything else of that nature",

            "We do not allow advertisements for communities (including other Discord servers) or "
            "commercial projects - Contact us directly if you want to discuss a partnership!"
        )
        self.default_desc = ("The rules and guidelines that apply to this community can be found on"
                             " our [rules page](https://pythondiscord.com/about/rules). We expect"
                             " all members of the community to have read and understood these."
                             )
        self.title_link = 'https://pythondiscord.com/about/rules'

    @command(aliases=['r', 'rule'], name='rules')
    @redirect_output(destination_channel=Channels.bot, bypass_roles=STAFF_ROLES)
    async def rules_command(self, ctx: Context, *, rules: Optional[str] = None):
        """
        Provides a link to the `rules` endpoint of the website, or displays
        specific rules, if they are requested.

        **`ctx`:** The Discord message context
        **`rules`:** The rules a user wants to get.
        """
        rules_embed = Embed(title='Rules', color=Colour.blurple())

        if not rules:
            # Rules were not submitted. Return the default description.
            rules_embed.description = self.default_desc
            rules_embed.url = 'https://pythondiscord.com/about/rules'
            return await ctx.send(embed=rules_embed)

        # Split the rules input by slash, comma or space
        # Returns a list of ints if they're in range of rules index
        rules_to_get = []
        split_rules = re.split(r'[/, ]', rules)
        for item in split_rules:
            if not item.isdigit():
                if not item:
                    continue
                rule_match = re.search(r'\d?\d[:|-]1?\d', item)
                if rule_match:
                    a, b = sorted([int(x)-1 for x in re.split(r'[:-]', rule_match.group())])
                    rules_to_get.extend(range(a, b+1))
            else:
                rules_to_get.append(int(item)-1)
        final_rules = [
            f'**{i+1}.** {self.rules[i]}' for i in sorted(rules_to_get) if i < len(self.rules)
        ]

        if not final_rules:
            # No valid rules in rules input. Return the default description.
            rules_embed.description = self.default_desc
            return await ctx.send(embed=rules_embed)
        await LinePaginator.paginate(
            final_rules, ctx, rules_embed,
            max_lines=3, url=self.title_link
        )


def setup(bot):
    bot.add_cog(Rules(bot))
