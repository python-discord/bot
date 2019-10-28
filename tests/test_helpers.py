import asyncio
import inspect
import unittest
import unittest.mock

import discord

from tests import helpers


class DiscordMocksTests(unittest.TestCase):
    """Tests for our specialized discord.py mocks."""

    def test_mock_role_default_initialization(self):
        """Test if the default initialization of MockRole results in the correct object."""
        role = helpers.MockRole()

        # The `spec` argument makes sure `isistance` checks with `discord.Role` pass
        self.assertIsInstance(role, discord.Role)

        self.assertEqual(role.name, "role")
        self.assertEqual(role.id, 1)
        self.assertEqual(role.position, 1)
        self.assertEqual(role.mention, "&role")

    def test_mock_role_alternative_arguments(self):
        """Test if MockRole initializes with the arguments provided."""
        role = helpers.MockRole(
            name="Admins",
            role_id=90210,
            position=10,
        )

        self.assertEqual(role.name, "Admins")
        self.assertEqual(role.id, 90210)
        self.assertEqual(role.position, 10)
        self.assertEqual(role.mention, "&Admins")

    def test_mock_role_accepts_dynamic_arguments(self):
        """Test if MockRole accepts and sets abitrary keyword arguments."""
        role = helpers.MockRole(
            guild="Dino Man",
            hoist=True,
        )

        self.assertEqual(role.guild, "Dino Man")
        self.assertTrue(role.hoist)

    def test_mock_role_uses_position_for_less_than_greater_than(self):
        """Test if `<` and `>` comparisons for MockRole are based on its position attribute."""
        role_one = helpers.MockRole(position=1)
        role_two = helpers.MockRole(position=2)
        role_three = helpers.MockRole(position=3)

        self.assertLess(role_one, role_two)
        self.assertLess(role_one, role_three)
        self.assertLess(role_two, role_three)
        self.assertGreater(role_three, role_two)
        self.assertGreater(role_three, role_one)
        self.assertGreater(role_two, role_one)

    def test_mock_member_default_initialization(self):
        """Test if the default initialization of Mockmember results in the correct object."""
        member = helpers.MockMember()

        # The `spec` argument makes sure `isistance` checks with `discord.Member` pass
        self.assertIsInstance(member, discord.Member)

        self.assertEqual(member.name, "member")
        self.assertEqual(member.id, 1)
        self.assertListEqual(member.roles, [helpers.MockRole("@everyone", 1)])
        self.assertEqual(member.mention, "@member")

    def test_mock_member_alternative_arguments(self):
        """Test if MockMember initializes with the arguments provided."""
        core_developer = helpers.MockRole("Core Developer", 2)
        member = helpers.MockMember(
            name="Mark",
            user_id=12345,
            roles=[core_developer]
        )

        self.assertEqual(member.name, "Mark")
        self.assertEqual(member.id, 12345)
        self.assertListEqual(member.roles, [helpers.MockRole("@everyone", 1), core_developer])
        self.assertEqual(member.mention, "@Mark")

    def test_mock_member_accepts_dynamic_arguments(self):
        """Test if MockMember accepts and sets abitrary keyword arguments."""
        member = helpers.MockMember(
            nick="Dino Man",
            colour=discord.Colour.default(),
        )

        self.assertEqual(member.nick, "Dino Man")
        self.assertEqual(member.colour, discord.Colour.default())

    def test_mock_guild_default_initialization(self):
        """Test if the default initialization of Mockguild results in the correct object."""
        guild = helpers.MockGuild()

        # The `spec` argument makes sure `isistance` checks with `discord.Guild` pass
        self.assertIsInstance(guild, discord.Guild)

        self.assertListEqual(guild.roles, [helpers.MockRole("@everyone", 1)])
        self.assertListEqual(guild.members, [])

    def test_mock_guild_alternative_arguments(self):
        """Test if MockGuild initializes with the arguments provided."""
        core_developer = helpers.MockRole("Core Developer", 2)
        guild = helpers.MockGuild(
            roles=[core_developer],
            members=[helpers.MockMember(user_id=54321)],
        )

        self.assertListEqual(guild.roles, [helpers.MockRole("@everyone", 1), core_developer])
        self.assertListEqual(guild.members, [helpers.MockMember(user_id=54321)])

    def test_mock_guild_accepts_dynamic_arguments(self):
        """Test if MockGuild accepts and sets abitrary keyword arguments."""
        guild = helpers.MockGuild(
            emojis=(":hyperjoseph:", ":pensive_ela:"),
            premium_subscription_count=15,
        )

        self.assertTupleEqual(guild.emojis, (":hyperjoseph:", ":pensive_ela:"))
        self.assertEqual(guild.premium_subscription_count, 15)

    def test_mock_bot_default_initialization(self):
        """Tests if MockBot initializes with the correct values."""
        bot = helpers.MockBot()

        # The `spec` argument makes sure `isistance` checks with `discord.ext.commands.Bot` pass
        self.assertIsInstance(bot, discord.ext.commands.Bot)

    def test_mock_context_default_initialization(self):
        """Tests if MockContext initializes with the correct values."""
        context = helpers.MockContext()

        # The `spec` argument makes sure `isistance` checks with `discord.ext.commands.Context` pass
        self.assertIsInstance(context, discord.ext.commands.Context)

        self.assertIsInstance(context.bot, helpers.MockBot)
        self.assertIsInstance(context.guild, helpers.MockGuild)
        self.assertIsInstance(context.author, helpers.MockMember)

    def test_mocks_allows_access_to_attributes_part_of_spec(self):
        """Accessing attributes that are valid for the objects they mock should succeed."""
        mocks = (
            (helpers.MockGuild(), 'name'),
            (helpers.MockRole(), 'hoist'),
            (helpers.MockMember(), 'display_name'),
            (helpers.MockBot(), 'user'),
            (helpers.MockContext(), 'invoked_with'),
            (helpers.MockTextChannel(), 'last_message'),
            (helpers.MockMessage(), 'mention_everyone'),
        )

        for mock, valid_attribute in mocks:
            with self.subTest(mock=mock):
                try:
                    getattr(mock, valid_attribute)
                except AttributeError:
                    msg = f"accessing valid attribute `{valid_attribute}` raised an AttributeError"
                    self.fail(msg)

    @unittest.mock.patch(f'{__name__}.DiscordMocksTests.subTest')
    @unittest.mock.patch(f'{__name__}.getattr')
    def test_mock_allows_access_to_attributes_test(self, mock_getattr, mock_subtest):
        """The valid attribute test should raise an AssertionError after an AttributeError."""
        mock_getattr.side_effect = AttributeError

        msg = "accessing valid attribute `name` raised an AttributeError"
        with self.assertRaises(AssertionError, msg=msg):
            self.test_mocks_allows_access_to_attributes_part_of_spec()

    def test_mocks_rejects_access_to_attributes_not_part_of_spec(self):
        """Accessing attributes that are invalid for the objects they mock should fail."""
        mocks = (
            helpers.MockGuild(),
            helpers.MockRole(),
            helpers.MockMember(),
            helpers.MockBot(),
            helpers.MockContext(),
            helpers.MockTextChannel(),
            helpers.MockMessage(),
        )

        for mock in mocks:
            with self.subTest(mock=mock):
                with self.assertRaises(AttributeError):
                    mock.the_cake_is_a_lie

    def test_custom_mock_methods_are_valid_discord_object_methods(self):
        """The `AsyncMock` attributes of the mocks should be valid for the class they're mocking."""
        mocks = (
            (helpers.MockGuild, helpers.guild_instance),
            (helpers.MockRole, helpers.role_instance),
            (helpers.MockMember, helpers.member_instance),
            (helpers.MockBot, helpers.bot_instance),
            (helpers.MockContext, helpers.context_instance),
            (helpers.MockTextChannel, helpers.channel_instance),
            (helpers.MockMessage, helpers.message_instance),
        )

        for mock_class, instance in mocks:
            mock = mock_class()
            async_methods = (
                attr for attr in dir(mock) if isinstance(getattr(mock, attr), helpers.AsyncMock)
            )

            # spec_mock = unittest.mock.MagicMock(spec=instance)
            for method in async_methods:
                with self.subTest(mock_class=mock_class, method=method):
                    try:
                        getattr(instance, method)
                    except AttributeError:
                        msg = f"method {method} is not a method attribute of {instance.__class__}"
                        self.fail(msg)

    @unittest.mock.patch(f'{__name__}.DiscordMocksTests.subTest')
    def test_the_custom_mock_methods_test(self, subtest_mock):
        """The custom method test should raise AssertionError for invalid methods."""
        class FakeMockBot(helpers.GetChildMockMixin, unittest.mock.MagicMock):
            """Fake MockBot class with invalid attribute/method `release_the_walrus`."""

            child_mock_type = unittest.mock.MagicMock

            def __init__(self, **kwargs):
                super().__init__(spec=helpers.bot_instance, **kwargs)

                # Fake attribute
                self.release_the_walrus = helpers.AsyncMock()

        with unittest.mock.patch("tests.helpers.MockBot", new=FakeMockBot):
            msg = "method release_the_walrus is not a valid method of <class 'discord.ext.commands.bot.Bot'>"
            with self.assertRaises(AssertionError, msg=msg):
                self.test_custom_mock_methods_are_valid_discord_object_methods()


class MockObjectTests(unittest.TestCase):
    """Tests the mock objects and mixins we've defined."""

    @classmethod
    def setUpClass(cls):
        cls.hashable_mocks = (helpers.MockRole, helpers.MockMember, helpers.MockGuild)

    def test_colour_mixin(self):
        """Test if the ColourMixin adds aliasing of color -> colour for child classes."""
        class MockHemlock(unittest.mock.MagicMock, helpers.ColourMixin):
            pass

        hemlock = MockHemlock()
        hemlock.color = 1
        self.assertEqual(hemlock.colour, 1)
        self.assertEqual(hemlock.colour, hemlock.color)

    def test_hashable_mixin_hash_returns_id(self):
        """Test if the HashableMixing uses the id attribute for hashing."""
        class MockScragly(unittest.mock.Mock, helpers.HashableMixin):
            pass

        scragly = MockScragly()
        scragly.id = 10
        self.assertEqual(hash(scragly), scragly.id)

    def test_hashable_mixin_uses_id_for_equality_comparison(self):
        """Test if the HashableMixing uses the id attribute for hashing."""
        class MockScragly(unittest.mock.Mock, helpers.HashableMixin):
            pass

        scragly = MockScragly(spec=object)
        scragly.id = 10
        eevee = MockScragly(spec=object)
        eevee.id = 10
        python = MockScragly(spec=object)
        python.id = 20

        self.assertTrue(scragly == eevee)
        self.assertFalse(scragly == python)

    def test_hashable_mixin_uses_id_for_nonequality_comparison(self):
        """Test if the HashableMixing uses the id attribute for hashing."""
        class MockScragly(unittest.mock.Mock, helpers.HashableMixin):
            pass

        scragly = MockScragly(spec=object)
        scragly.id = 10
        eevee = MockScragly(spec=object)
        eevee.id = 10
        python = MockScragly(spec=object)
        python.id = 20

        self.assertTrue(scragly != python)
        self.assertFalse(scragly != eevee)

    def test_mock_class_with_hashable_mixin_uses_id_for_hashing(self):
        """Test if the MagicMock subclasses that implement the HashableMixin use id for hash."""
        for mock in self.hashable_mocks:
            with self.subTest(mock_class=mock):
                instance = helpers.MockRole(role_id=100)
                self.assertEqual(hash(instance), instance.id)

    def test_mock_class_with_hashable_mixin_uses_id_for_equality(self):
        """Test if MagicMocks that implement the HashableMixin use id for equality comparisons."""
        for mock_class in self.hashable_mocks:
            with self.subTest(mock_class=mock_class):
                instance_one = mock_class()
                instance_two = mock_class()
                instance_three = mock_class()

                instance_one.id = 10
                instance_two.id = 10
                instance_three.id = 20

                self.assertTrue(instance_one == instance_two)
                self.assertFalse(instance_one == instance_three)

    def test_mock_class_with_hashable_mixin_uses_id_for_nonequality(self):
        """Test if MagicMocks that implement HashableMixin use id for nonequality comparisons."""
        for mock_class in self.hashable_mocks:
            with self.subTest(mock_class=mock_class):
                instance_one = mock_class()
                instance_two = mock_class()
                instance_three = mock_class()

                instance_one.id = 10
                instance_two.id = 10
                instance_three.id = 20

                self.assertFalse(instance_one != instance_two)
                self.assertTrue(instance_one != instance_three)

    def test_get_child_mock_mixin_accepts_mock_seal(self):
        """The `GetChildMockMixin` should support `unittest.mock.seal`."""
        class MyMock(helpers.GetChildMockMixin, unittest.mock.MagicMock):

            child_mock_type = unittest.mock.MagicMock
            pass

        mock = MyMock()
        unittest.mock.seal(mock)
        with self.assertRaises(AttributeError, msg="MyMock.shirayuki"):
            mock.shirayuki = "hello!"

    def test_spec_propagation_of_mock_subclasses(self):
        """Test if the `spec` does not propagate to attributes of the mock object."""
        test_values = (
            (helpers.MockGuild, "region"),
            (helpers.MockRole, "mentionable"),
            (helpers.MockMember, "display_name"),
            (helpers.MockBot, "owner_id"),
            (helpers.MockContext, "command_failed"),
        )

        for mock_type, valid_attribute in test_values:
            with self.subTest(mock_type=mock_type, attribute=valid_attribute):
                mock = mock_type()
                self.assertTrue(isinstance(mock, mock_type))
                attribute = getattr(mock, valid_attribute)
                self.assertTrue(isinstance(attribute, mock_type.child_mock_type))

    def test_async_mock_provides_coroutine_for_dunder_call(self):
        """Test if AsyncMock objects have a coroutine for their __call__ method."""
        async_mock = helpers.AsyncMock()
        self.assertTrue(inspect.iscoroutinefunction(async_mock.__call__))

        coroutine = async_mock()
        self.assertTrue(inspect.iscoroutine(coroutine))
        self.assertIsNotNone(asyncio.run(coroutine))

    def test_async_test_decorator_allows_synchronous_call_to_async_def(self):
        """Test if the `async_test` decorator allows an `async def` to be called synchronously."""
        @helpers.async_test
        async def kosayoda():
            return "return value"

        self.assertEqual(kosayoda(), "return value")
