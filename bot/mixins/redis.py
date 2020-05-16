import redis as redis_py

redis = redis_py.Redis(host="redis")


class RedisDict(dict):
    """
    A dictionary interface for a Redis database.

    Objects created by this class should mostly behave like a normal dictionary,
    but will store all the data in our Redis database for persistence between restarts.

    There are, however, a few limitations to what kinds of data types can be
    stored on Redis, so this is a little bit more limited than a regular dict.
    """

    def __init__(self, namespace: str = "global"):
        """Initialize the RedisDict with the right namespace."""
        # TODO: Make namespace collision impossible!
        #       Append a number or something if it exists already.
        self.namespace = namespace

    # redis.mset({"firedog": "donkeykong"})
    #
    # print(redis.get("firedog").decode("utf-8")


class RedisCacheMixin:
    """
    A mixin which adds a cls.cache parameter which can be used for persistent caching.

    This adds a dictionary-like object called cache which can be treated like a regular dictionary,
    but which can only store simple data types like ints, strings, and floats.

    To use it, simply subclass it into your class like this:

    class MyCog(Cog, RedisCacheMixin):
        def some_command(self):
            # You can now do this!
            self.cache['some_data'] = some_data

    All the data stored in this cache will probably be available permanently, even if the bot restarts or
    is updated. However, Redis is not meant to be used for reliable, permanent storage. It may be cleared
    from time to time, so please only use it for caching data that you can afford to lose.

    If it's really important that your data should never disappear, please use our postgres database instead.
    """

    def __init_subclass__(cls, **kwargs):
        """
        Initialize the cache when subclass is created.

        When this mixin is subclassed, we create a cache using the subclass name as the namespace.
        This is to prevent collisions between subclasses.
        """
        cls.cache = RedisDict(cls.__name__)
