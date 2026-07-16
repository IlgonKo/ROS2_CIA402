class CommandRouter:
    """Maps protocol command names to application command functions."""

    def __init__(self, routes):
        self._routes = dict(routes)

    def dispatch(self, command_name, message, runtime, state, client):
        command = self._routes.get(command_name)
        if command is None:
            return False
        command(message, runtime, state, client)
        return True

    @property
    def command_names(self):
        return frozenset(self._routes)
