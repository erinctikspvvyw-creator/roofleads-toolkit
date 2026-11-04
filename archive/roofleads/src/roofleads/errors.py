class ConfigError(Exception):
    """The operator can fix this by editing config, env, or inputs."""


class ApiError(Exception):
    """A remote API failed after the local checks and retries."""


class ExportError(Exception):
    """The delivery file was refused because a row was not ready to ship."""
