export type UserRole = 'customer_developer' | 'tenant_admin' | 'support_agent' | 'knowledge_admin'

export interface CurrentUser {
  id: string
  tenant_id: string | null
  email: string
  display_name: string
  role: UserRole
}

export interface TraceEvent {
  sequence: number
  node: string
  status: 'succeeded' | 'degraded' | 'denied'
  detail: string
}

export interface Citation {
  document_id: string
  chunk_id: string
  title: string
  source_uri: string
  excerpt: string
  score: number
}

export interface TicketDraft {
  summary: string
  description: string
  category: TicketCategory
  severity: TicketSeverity
  escalation_reason: string
  requires_confirmation: true
}

export interface AgentResponse {
  request_id: string
  session_id: string
  trace_id: string
  outcome: 'answered' | 'needs_clarification' | 'needs_confirmation' | 'escalated' | 'refused' | 'cancelled'
  intent: string
  risk_level: 'R1' | 'R2' | 'R3'
  message: string
  response_mode: string
  citations: Citation[]
  tool_result: Record<string, unknown> | null
  ticket_draft: TicketDraft | null
  required_fields: string[]
  escalation_reason: string | null
  conversation_status: string
  model_usage: {
    model_calls: number
    total_tokens: number
    estimated_cost_cny: number
  }
  trace: TraceEvent[]
}

export type TicketStatus = 'open' | 'triaged' | 'in_progress' | 'waiting_customer' | 'resolved' | 'closed'
export type TicketSeverity = 'low' | 'medium' | 'high' | 'urgent'
export type TicketCategory = 'authentication' | 'entitlement' | 'quota' | 'incident' | 'integration' | 'other'

export interface TicketTransition {
  id: string
  from_status: TicketStatus
  to_status: TicketStatus
  actor_id: string
  reason: string
  created_at: string
}

export interface Ticket {
  id: string
  public_code: string
  tenant_id: string
  status: TicketStatus
  severity: TicketSeverity
  category: TicketCategory
  summary: string
  description: string
  diagnostic_context: Record<string, unknown>
  escalation_reason: string
  assignee_id: string | null
  agent_run_id: string | null
  version: number
  created_at: string
  updated_at: string
  transitions: TicketTransition[]
  replayed: boolean
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string }
}
