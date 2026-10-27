"""Session cache module with intentional mutable default argument bug for testing."""

class SessionCache:
    """Manages active user session tokens."""

    def __init__(self):
        self.name = "default_cache"

    def add_to_session(self, key: str, value: str, items=None):
        if items is None:
            items = []
        """Adds key-value pair to user session list.
        
        Bug: items=[] mutable default leaks entries across distinct user calls!
        """
        items.append((key, value))
        return items
