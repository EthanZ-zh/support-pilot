class DomainError(Exception):
    """Base class for expected business failures."""

    status_code = 400
    code = "domain_error"


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_required"


class AuthorizationError(DomainError):
    status_code = 403
    code = "tenant_access_denied"


class ResourceNotFoundError(DomainError):
    status_code = 404
    code = "resource_not_found"


class RequestPreconditionError(DomainError):
    status_code = 400
    code = "request_precondition_failed"


class IdempotencyConflictError(DomainError):
    status_code = 409
    code = "idempotency_key_conflict"


class IdempotencyInProgressError(DomainError):
    status_code = 409
    code = "idempotency_request_in_progress"


class InvalidTransitionError(DomainError):
    status_code = 409
    code = "invalid_ticket_transition"


class ConcurrencyConflictError(DomainError):
    status_code = 409
    code = "concurrency_conflict"


class AssignmentConflictError(DomainError):
    status_code = 409
    code = "ticket_assignment_conflict"


class ProviderUnavailableError(DomainError):
    status_code = 503
    code = "provider_unavailable"
