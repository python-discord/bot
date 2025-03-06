import unittest
import time

from bot.exts.stalking_system.spam_check import RateLimiter

class TestRateLimiter(unittest.TestCase):
    def setUp(self):
        """Initialize a RateLimiter instance before each test."""
        self.limiter = RateLimiter(message_threshold=3, time_window=10)

    def test_below_threshold(self):
        """User should not be marked as malicious when staying below the threshold."""
        user_id = 1
        current_time = time.time()

        self.limiter.record_trigger(user_id, current_time)
        self.limiter.record_trigger(user_id, current_time + 2)
        
        self.assertFalse(self.limiter.is_malicious(user_id, current_time + 3))

    def test_exceed_threshold(self):
        """User should be marked as malicious when exceeding the threshold within the time window."""
        user_id = 2
        current_time = time.time()

        self.limiter.record_trigger(user_id, current_time)
        self.limiter.record_trigger(user_id, current_time + 2)
        self.limiter.record_trigger(user_id, current_time + 3)

        self.assertTrue(self.limiter.is_malicious(user_id, current_time + 4))

    def test_old_messages_are_ignored(self):
        """Messages outside the time window should not count towards the limit."""
        user_id = 3
        current_time = time.time()

        self.limiter.record_trigger(user_id, current_time - 15)  # Old message
        self.limiter.record_trigger(user_id, current_time - 12)  # Old message
        self.limiter.record_trigger(user_id, current_time)
        
        self.assertFalse(self.limiter.is_malicious(user_id, current_time + 1))

    def test_independent_users(self):
        """Each user should have their own independent rate limit tracking."""
        user1 = 4
        user2 = 5
        current_time = time.time()

        self.limiter.record_trigger(user1, current_time)
        self.limiter.record_trigger(user1, current_time + 2)
        self.limiter.record_trigger(user1, current_time + 3)

        self.assertTrue(self.limiter.is_malicious(user1, current_time + 4))
        self.assertFalse(self.limiter.is_malicious(user2, current_time + 4))  # User2 has no triggers

