from bot.bot import Bot
from .incidents import Incidents
from .infraction.infractions import Infractions
from .infraction.management import ModManagement
from .infraction.superstarify import Superstarify
from .modlog import ModLog
from .silence import Silence
from .slowmode import Slowmode


def setup(bot: Bot) -> None:
    """Load the Incidents, Infractions, ModManagement, ModLog, Silence, Slowmode and Superstarify cogs."""
    bot.add_cog(Incidents(bot))
    bot.add_cog(Infractions(bot))
    bot.add_cog(ModLog(bot))
    bot.add_cog(ModManagement(bot))
    bot.add_cog(Silence(bot))
    bot.add_cog(Slowmode(bot))
    bot.add_cog(Superstarify(bot))
