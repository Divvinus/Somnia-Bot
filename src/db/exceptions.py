class DatabaseError(Exception):
    """Used for database errors."""

class ConnectionError(DatabaseError):
    """Occurs when it is not possible to establish a connection to the database."""

class RouteNotFoundError(DatabaseError):
    """Occurs when the route is not found for the specified account and name."""