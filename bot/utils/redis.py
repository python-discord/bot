from collections.abc import MutableMapping
from typing import Optional

import redis as redis_py

redis = redis_py.Redis(host="redis")


class RedisDict(MutableMapping):
    """
    A dictionary interface for a Redis database.

    Objects created by this class should mostly behave like a normal dictionary,
    but will store all the data in our Redis database for persistence between restarts.

    Redis is limited to simple types, so to allow you to store collections like lists
    and dictionaries, we JSON deserialize every value. That means that it will not be possible
    to store complex objects, only stuff like strings, numbers, and collections of strings and numbers.

    TODO: Implement these:
          __delitem__
          __getitem__
          __setitem__
          __iter__
          __len__
          clear (just use DEL and the hash goes)
          copy (convert to dict maybe?)
          pop
          popitem
          setdefault
          update

    TODO: TEST THESE
          .get
          .items
          .keys
          .values
          .__eg__
          .__ne__
    """

    namespaces = []

    def _set_namespace(self, namespace: str) -> None:
        """Try to set the namespace, but do not permit collisions."""
        while namespace in self.namespaces:
            namespace = namespace + "_"

        self.namespaces.append(namespace)
        self.namespace = namespace

    def __init__(self, namespace: Optional[str] = None) -> None:
        """Initialize the RedisDict with the right namespace."""
        super().__init__()
        self.has_custom_namespace = namespace is not None
        self._set_namespace(namespace)

    def __set_name__(self, owner: object, attribute_name: str) -> None:
        """
        Set the namespace to Class.attribute_name.

        Called automatically when this class is constructed inside a class as an attribute, as long as
        no custom namespace is provided to the constructor.
        """
        if not self.has_custom_namespace:
            self._set_namespace(f"{owner.__name__}.{attribute_name}")

    def __repr__(self) -> str:
        """Return a beautiful representation of this object instance."""
        return f"RedisDict(namespace={self.namespace!r})"
