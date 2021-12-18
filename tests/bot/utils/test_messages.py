import unittest
from unittest.mock import AsyncMock, patch

from bot.utils import messages, regex
from tests.helpers import MockMessage


class TestMessages(unittest.TestCase):
    """Tests for functions in the `bot.utils.messages` module."""

    def test_sub_clyde(self):
        """Uppercase E's and lowercase e's are substituted with their cyrillic counterparts."""
        sub_e = "\u0435"
        sub_E = "\u0415"  # noqa: N806: Uppercase E in variable name

        test_cases = (
            (None, None),
            ("", ""),
            ("clyde", f"clyd{sub_e}"),
            ("CLYDE", f"CLYD{sub_E}"),
            ("cLyDe", f"cLyD{sub_e}"),
            ("BIGclyde", f"BIGclyd{sub_e}"),
            ("small clydeus the unholy", f"small clyd{sub_e}us the unholy"),
            ("BIGCLYDE, babyclyde", f"BIGCLYD{sub_E}, babyclyd{sub_e}"),
        )

        for username_in, username_out in test_cases:
            with self.subTest(input=username_in, expected_output=username_out):
                self.assertEqual(messages.sub_clyde(username_in), username_out)

    def test_shorten_text(self):
        """Test all cases of text shortening by mocking messages."""
        tests = {
            "thisisasingleword"
            * 10: "thisisasinglewordthisisasinglewordthisisasinglewor...",
            "\n".join("Lets make a new line test".split()): "Lets\nmake\na...",
            "Hello, World!"
            * 300: (
                "Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!"
                "Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!"
                "Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!Hello, World!"
                "Hello, World!Hello, World!H..."
            ),
        }

        for content, expected_conversion in tests.items():
            with self.subTest(content=content, expected_conversion=expected_conversion):
                conversion = messages.shorten_text(content)
                self.assertEqual(conversion, expected_conversion)

    def test_extract_valid_message_links(self):
        """Test message link detection regex."""
        test_links = (
            "https://discord.com/channels/884793126525489203/884793128073195592/921717920869003294",
            "http://discord.com/channels/884793126525489203/884793128073195592/921717920869003294",
            "http://www.discord.com/channels/884793126525489203/884793128073195592/921717920869003294",
            "http://ptb.discord.com/channels/884793126525489203/884793128073195592/921717920869003294",
            "http://canary.discordapp.com/channels/884793126525489203/884793128073195592/921717920869003294",
        )

        for link in test_links:
            with self.subTest(token=link):
                results = regex.DISCORD_MESSAGE_LINK_RE.fullmatch(link)
                self.assertIsNotNone(
                    results, f"Valid link '{link}' was not matched by the regex"
                )

    def test_extract_invalid_message_links(self):
        """Test message link detection regex."""
        test_links = (
            "https://discord.com/channels/884793126525489203/884793128073195592/921717920869003294",
            "http:/discord.com/channels/884793126525489203/884793128073195592/9217179208609003294",
            "http://ptb.discord.com/channels/8847931265254203/884793128073195592/921717920869003294",
            "http://canary.discord.app/channels/884793126525489203/884793128073195592/921717920869003294",
        )

        for link in test_links:
            with self.subTest(token=link):
                results = regex.DISCORD_MESSAGE_LINK_RE.findall(link)
                self.assertEqual(
                    len(results), 0, f"Invalid link '{link}' was matched by the regex"
                )

    async def test_msg_link_embed_formation(self):
        msg = MockMessage(id=555, content="Hello, World!" * 3000)
        msg.channel.mention = "#ot0-tim-curry-the-inventor-of-haskell"

        incident_msg = MockMessage(
            id=777,
            content=(
                f"Looks like someone is spamming IP loggers in ot0, here is the link: "
                f"https://discord.com/channels/267624335836053506/{msg.channel.discord_id}/{msg.discord_id}"
            ),
        )

        with patch(
            "bot.exts.moderation.incidents.Incidents.extract_message_links", AsyncMock()
        ) as mock_extract_message_links:
            embeds = mock_extract_message_links(incident_msg)
            description = (
                f"**Author:** {messages.format_user(msg.author)}\n"
                f"**Channel:** {msg.channel.mention} ({msg.channel.category}/#{msg.channel.name})\n"
                f"**Content:** {('Hello, World!' * 3000)[:300] + '...'}\n"
            )

            # Check number of embeds returned with number of valid links
            self.assertEqual(len(embeds), 2)

            # Check for the embed descriptions
            for embed in embeds:
                self.assertEqual(embed.description, description)
