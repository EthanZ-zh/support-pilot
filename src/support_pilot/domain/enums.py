from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER_DEVELOPER = "customer_developer"
    TENANT_ADMIN = "tenant_admin"
    SUPPORT_AGENT = "support_agent"
    KNOWLEDGE_ADMIN = "knowledge_admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class Intent(StrEnum):
    ENTITLEMENT = "entitlement"
    QUOTA = "quota"
    INCIDENT = "incident"
    TICKET_REQUEST = "ticket_request"
    HIGH_RISK = "high_risk"


class RiskLevel(StrEnum):
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class RequestStatus(StrEnum):
    RECEIVED = "received"
    RUNNING = "running"
    ANSWERED = "answered"
    ESCALATED = "escalated"
    FAILED = "failed"
    REFUSED = "refused"


class TicketStatus(StrEnum):
    OPEN = "open"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(StrEnum):
    AUTHENTICATION = "authentication"
    ENTITLEMENT = "entitlement"
    QUOTA = "quota"
    INCIDENT = "incident"
    INTEGRATION = "integration"
    OTHER = "other"


class EscalationReason(StrEnum):
    USER_REQUESTED = "user_requested"
    LOW_ANSWERABILITY = "low_answerability"
    HIGH_RISK = "high_risk"
    TOOL_FAILURE = "tool_failure"
    SECURITY_OR_PRIVACY = "security_or_privacy"
    UNKNOWN = "unknown"


class IncidentStatus(StrEnum):
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class IdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResponseOutcome(StrEnum):
    ANSWERED = "answered"
    ESCALATED = "escalated"
    REFUSED = "refused"
