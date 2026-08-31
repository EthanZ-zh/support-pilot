import type { AgentResponse, ApiErrorBody, CurrentUser, Ticket, TraceEvent } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
  ) {
    super(message)
  }
}

async function parseError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as ApiErrorBody
  return new ApiError(
    body.error?.message ?? `请求失败 (${response.status})`,
    body.error?.code ?? 'request_failed',
    response.status,
  )
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  })
  if (!response.ok) throw await parseError(response)
  return response.json() as Promise<T>
}

export async function login(email: string, password: string): Promise<string> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) throw await parseError(response)
  const body = (await response.json()) as { access_token: string }
  return body.access_token
}

export const getCurrentUser = (token: string) => request<CurrentUser>('/auth/me', token)

interface StreamCallbacks {
  onProgress: (event: TraceEvent) => void
  onResult: (result: AgentResponse) => void
}

export async function streamAgent(
  token: string,
  payload: Record<string, unknown>,
  callbacks: StreamCallbacks,
  idempotencyKey?: string,
): Promise<void> {
  const response = await fetch(`${API_BASE}/agent/resolve/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${token}`,
      ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw await parseError(response)
  if (!response.body) throw new ApiError('浏览器没有收到事件流', 'stream_unavailable', 0)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) dispatchSseBlock(block, callbacks)
    if (done) break
  }
  if (buffer.trim()) dispatchSseBlock(buffer, callbacks)
}

function dispatchSseBlock(block: string, callbacks: StreamCallbacks): void {
  let eventName = 'message'
  const dataLines: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (!dataLines.length) return
  const payload = JSON.parse(dataLines.join('\n')) as unknown
  if (eventName === 'progress') callbacks.onProgress(payload as TraceEvent)
  if (eventName === 'result') callbacks.onResult(payload as AgentResponse)
  if (eventName === 'error') {
    const body = payload as ApiErrorBody
    throw new ApiError(body.error?.message ?? 'Agent 执行失败', body.error?.code ?? 'agent_failed', 200)
  }
}

export const listTickets = (token: string) =>
  request<{ items: Ticket[]; total: number }>('/tickets?limit=100', token)

export const claimTicket = (token: string, ticket: Ticket) =>
  request<Ticket>(`/tickets/${ticket.id}/claim`, token, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ expected_version: ticket.version }),
  })

export const transitionTicket = (
  token: string,
  ticket: Ticket,
  toStatus: string,
  reason: string,
) =>
  request<Ticket>(`/tickets/${ticket.id}/transitions`, token, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ to_status: toStatus, expected_version: ticket.version, reason }),
  })

export const submitFeedback = (
  token: string,
  ticket: Ticket,
  payload: Record<string, unknown>,
) =>
  request(`/tickets/${ticket.id}/feedback`, token, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify(payload),
  })
