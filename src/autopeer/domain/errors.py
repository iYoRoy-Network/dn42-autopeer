class AutopeerError(Exception):
    """Base class for domain errors."""


class NotFoundError(AutopeerError):
    pass


class ConflictError(AutopeerError):
    pass


class ValidationError(AutopeerError):
    pass
