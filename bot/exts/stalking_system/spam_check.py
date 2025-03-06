# spam_check.py
# Message with spam is already filtered by filtering extention.
# So this class checks if a user triggers the track function too many times maliciously.
from collections import deque

class RateLimiter:
    def __init__(self, message_threshold=3, time_window=10):
        """
        Initialize the rate limiter.

        :param message_threshold: Maximum allowed triggers within the time window.
        :param time_window: Time window size (in seconds).
        """
        self.message_threshold = message_threshold
        self.time_window = time_window
        self.user_message_timestamps = {}

    def is_malicious(self, user_id: int, timestamp: float) -> bool:
        """
        Check if a user is triggering messages maliciously.

        :param user_id: User ID.
        :param timestamp: Current timestamp.
        :param word: Triggered word (for potential future analysis).
        :return: True if the user is exceeding the allowed trigger limit, False otherwise.
        """
        if user_id not in self.user_message_timestamps:
            return False

        timestamps = self.user_message_timestamps[user_id]

        while timestamps and timestamps[0] < timestamp - self.time_window:
            timestamps.popleft()

        return len(timestamps) >= self.message_threshold

    def record_trigger(self, user_id: int, timestamp: float) -> None:
        """
        Record a successful trigger for a user.

        :param user_id: User ID.
        :param timestamp: Time when the trigger occurred.
        :param word: Triggered word.
        """
        if user_id not in self.user_message_timestamps:
            self.user_message_timestamps[user_id] = deque()

        self.user_message_timestamps[user_id].append(timestamp)