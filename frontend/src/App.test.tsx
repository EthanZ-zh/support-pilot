import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const customer = {
  id: '10000000-0000-0000-0000-000000000001',
  tenant_id: '20000000-0000-0000-0000-000000000001',
  email: 'alpha.admin@example.com',
  display_name: 'Alpha Admin',
  role: 'tenant_admin',
}

const supportAgent = {
  ...customer,
  id: '30000000-0000-0000-0000-000000000001',
  tenant_id: null,
  email: 'support.agent@example.com',
  display_name: 'Support Agent',
  role: 'support_agent',
}

const ticket = {
  id: '40000000-0000-0000-0000-000000000001', public_code: 'SP-1001', tenant_id: customer.tenant_id,
  status: 'open', severity: 'high', category: 'incident', summary: 'Webhook delivery failed',
  description: 'Callbacks have failed since 10:00.', diagnostic_context: { component_code: 'webhook' },
  escalation_reason: 'user_requested', assignee_id: null, agent_run_id: null, version: 1,
  created_at: '2026-08-31T10:00:00Z', updated_at: '2026-08-31T10:00:00Z', transitions: [], replayed: false,
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

function sseResponse(): Response {
  const body = [
    'event: progress\ndata: {"sequence":1,"node":"preflight_safety","status":"succeeded","detail":"safe"}\n\n',
    'event: result\ndata: {"request_id":"r","session_id":"s","trace_id":"trace-123456789","outcome":"answered","intent":"knowledge","risk_level":"R1","message":"请按 Retry-After 等待后重试。","response_mode":"extractive","citations":[],"tool_result":null,"ticket_draft":null,"required_fields":[],"escalation_reason":null,"conversation_status":"completed","model_usage":{"model_calls":0,"total_tokens":0,"estimated_cost_cny":0},"trace":[]}\n\n',
  ].join('')
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

afterEach(() => {
  localStorage.clear()
  vi.unstubAllGlobals()
})

describe('SupportPilot console', () => {
  it('renders live Agent progress and the final evidence-led answer', async () => {
    localStorage.setItem('support-pilot-token', 'customer-token')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return jsonResponse(customer)
      if (url.endsWith('/agent/resolve/stream')) return sseResponse()
      throw new Error(`unexpected request: ${url}`)
    }))
    render(<App />)

    await screen.findByText('Alpha Admin')
    await userEvent.click(screen.getByRole('button', { name: '开始诊断' }))

    expect(await screen.findByText('请按 Retry-After 等待后重试。')).toBeInTheDocument()
    expect(screen.getByText('preflight_safety')).toBeInTheDocument()
  })

  it('lets a support agent claim an open handoff ticket', async () => {
    localStorage.setItem('support-pilot-token', 'support-token')
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/auth/me')) return jsonResponse(supportAgent)
      if (url.includes('/tickets?')) return jsonResponse({ items: [ticket], total: 1 })
      if (url.endsWith(`/tickets/${ticket.id}/claim`)) {
        return jsonResponse({ ...ticket, status: 'triaged', assignee_id: supportAgent.id, version: 2, transitions: [{ id: 't1', from_status: 'open', to_status: 'triaged', actor_id: supportAgent.id, reason: 'ticket_claimed', created_at: '2026-08-31T10:01:00Z' }] })
      }
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    await screen.findByRole('heading', { name: 'Webhook delivery failed' })
    await userEvent.click(screen.getByRole('button', { name: '认领并分诊' }))

    await waitFor(() => expect(screen.getAllByText('triaged')).not.toHaveLength(0))
    expect(screen.getByText('open → triaged')).toBeInTheDocument()
  })
})
