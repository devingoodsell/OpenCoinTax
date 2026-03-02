class AppError(Exception):
    """Base class for all domain errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(AppError):
    """Raised when a requested resource does not exist."""

    def __init__(self, entity: str, identifier: str | int):
        self.entity = entity
        self.identifier = str(identifier)
        super().__init__(f"{entity} {self.identifier} not found")


class ValidationError(AppError):
    """Raised when input fails business validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


class ConflictError(AppError):
    """Raised when an operation conflicts with current state."""
    pass


class ExternalServiceError(AppError):
    """Raised when an external API fails."""

    def __init__(self, service: str, message: str):
        self.service = service
        super().__init__(f"{service}: {message}")


class ImportSessionExpiredError(AppError):
    """Raised when an import session has expired."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"Import session {session_id} has expired")
