import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  ApiError,
  claimTicket,
  getCurrentUser,
  listTickets,
  login,
  streamAgent,
  submitFeedback,
  transitionTicket,
} from './api'
import type { AgentResponse, CurrentUser, Ticket, TicketStatus, TraceEvent } from './types'
import './styles.css'

const TOKEN_KEY = 'support-pilot-token'

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误'
}

function Login({ onAuthenticated }: { onAuthenticated: (token: string, user: CurrentUser) => void }) {
  const [email, setEmail] = useState('alpha.admin@example.com')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const token = await login(email, password)
      const user = await getCurrentUser(token)
      localStorage.setItem(TOKEN_KEY, token)
      onAuthenticated(token, user)
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login-shell">
      <section className="login-copy">
        <div className="brand-mark">SP</div>
        <p className="eyebrow">SupportPilot · AI support operations</p>
        <h1>让每次技术支持都有证据、有边界、有接管路径。</h1>
        <p className="lede">检索企业知识与业务状态，经过置信度门控后自动回答或安全升级人工。</p>
        <div className="flow-strip"><span>识别</span><span>检索 / 工具</span><span>门控</span><span>人工闭环</span></div>
      </section>
      <form className="login-card" onSubmit={submit}>
        <p className="eyebrow">本地演示环境</p>
        <h2>登录控制台</h2>
        <label>邮箱<input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required /></label>
        <label>密码<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required minLength={8} /></label>
        {error && <p className="error-banner" role="alert">{error}</p>}
        <button className="primary" disabled={busy}>{busy ? '验证中…' : '进入工作台'}</button>
        <small>JWT 仅保存在当前浏览器；退出后立即移除。</small>
      </form>
    </main>
  )
}

function TraceTimeline({ events }: { events: TraceEvent[] }) {
  return (
    <ol className="trace-list" aria-label="Agent 执行轨迹">
      {events.map((event) => <li key={`${event.sequence}-${event.node}`} className={event.status}>
        <span>{event.sequence}</span><div><strong>{event.node}</strong><p>{event.detail}</p></div>
      </li>)}
    </ol>
  )
}

function CustomerWorkspace({ token }: { token: string }) {
  const [message, setMessage] = useState('HTTP 429 响应里的 Retry-After 应该如何处理？')
  const [featureCode, setFeatureCode] = useState('')
  const [metricCode, setMetricCode] = useState('')
  const [sessionId] = useState(() => crypto.randomUUID())
  const [trace, setTrace] = useState<TraceEvent[]>([])
  const [result, setResult] = useState<AgentResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function execute(confirmation?: 'confirm_ticket' | 'cancel_ticket') {
    setBusy(true)
    setError('')
    setTrace([])
    const payload: Record<string, unknown> = {
      session_id: sessionId,
      message: confirmation ? (confirmation === 'confirm_ticket' ? '确认创建工单' : '取消创建工单') : message,
      context: {
        ...(featureCode ? { feature_code: featureCode } : {}),
        ...(metricCode ? { metric_code: metricCode } : {}),
      },
      ...(confirmation ? { confirmation } : {}),
    }
    try {
      await streamAgent(token, payload, {
        onProgress: (event) => setTrace((current) => [...current, event]),
        onResult: setResult,
      }, confirmation === 'confirm_ticket' ? crypto.randomUUID() : undefined)
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="workspace-grid customer-grid">
      <section className="panel compose-panel">
        <p className="eyebrow">客户问题</p>
        <h2>描述你遇到的问题</h2>
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={6} />
        <details><summary>补充结构化上下文</summary><div className="field-grid">
          <label>功能编码<input value={featureCode} onChange={(event) => setFeatureCode(event.target.value)} placeholder="bulk_export" /></label>
          <label>指标编码<input value={metricCode} onChange={(event) => setMetricCode(event.target.value)} placeholder="api_calls" /></label>
        </div></details>
        <button className="primary" onClick={() => execute()} disabled={busy || message.length < 2}>{busy ? 'Agent 正在诊断…' : '开始诊断'}</button>
        {error && <p className="error-banner" role="alert">{error}</p>}
        <div className="session-note">Session · {sessionId.slice(0, 8)}</div>
      </section>
      <section className="panel result-panel">
        <div className="panel-heading"><div><p className="eyebrow">受控响应</p><h2>诊断结果</h2></div>{result && <span className={`risk ${result.risk_level}`}>{result.risk_level}</span>}</div>
        {!result && !trace.length && <div className="empty-state">提交问题后，这里会展示回答、证据和逐节点执行轨迹。</div>}
        {result && <>
          <div className={`outcome ${result.outcome}`}><span>{result.outcome}</span><strong>{result.intent}</strong></div>
          <p className="answer">{result.message}</p>
          {result.ticket_draft && <div className="ticket-draft"><p className="eyebrow">写操作确认</p><h3>{result.ticket_draft.summary}</h3><p>{result.ticket_draft.description}</p><div className="button-row"><button className="primary" onClick={() => execute('confirm_ticket')} disabled={busy}>确认创建工单</button><button className="ghost" onClick={() => execute('cancel_ticket')} disabled={busy}>取消</button></div></div>}
          {!!result.citations.length && <div className="evidence"><h3>引用证据</h3>{result.citations.map((citation, index) => <article key={citation.chunk_id}><span>{String(index + 1).padStart(2, '0')}</span><div><strong>{citation.title}</strong><p>{citation.excerpt}</p><code>{citation.source_uri}</code></div></article>)}</div>}
          <div className="run-meta"><span>Trace {result.trace_id.slice(0, 10)}</span><span>{result.model_usage.model_calls} model calls</span><span>{result.model_usage.total_tokens} tokens</span></div>
        </>}
      </section>
      <aside className="panel trace-panel"><p className="eyebrow">Live trace</p><h2>执行轨迹</h2>{trace.length ? <TraceTimeline events={trace} /> : <p className="muted">等待节点事件…</p>}</aside>
    </div>
  )
}

const NEXT_STATUS: Partial<Record<TicketStatus, TicketStatus[]>> = {
  triaged: ['in_progress'],
  in_progress: ['waiting_customer', 'resolved'],
  waiting_customer: ['in_progress', 'resolved'],
  resolved: ['closed', 'in_progress'],
}

function SupportWorkspace({ token, user }: { token: string; user: CurrentUser }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const selected = useMemo(() => tickets.find((ticket) => ticket.id === selectedId) ?? tickets[0] ?? null, [tickets, selectedId])

  const refresh = useCallback(async () => {
    try {
      const response = await listTickets(token)
      setTickets(response.items)
    } catch (caught) { setError(messageFrom(caught)) }
  }, [token])
  useEffect(() => {
    listTickets(token)
      .then((response) => setTickets(response.items))
      .catch((caught: unknown) => setError(messageFrom(caught)))
  }, [token])

  function replace(ticket: Ticket) {
    setTickets((current) => current.map((item) => item.id === ticket.id ? ticket : item))
  }
  async function mutate(action: () => Promise<Ticket>) {
    setBusy(true); setError('')
    try { replace(await action()) } catch (caught) { setError(messageFrom(caught)); await refresh() } finally { setBusy(false) }
  }

  return (
    <div className="support-layout">
      <aside className="queue-panel"><div className="queue-heading"><div><p className="eyebrow">Human handoff</p><h2>工单队列</h2></div><button className="icon-button" onClick={refresh} aria-label="刷新工单">↻</button></div>
        <div className="queue-count">{tickets.length} 个待查看工单</div>
        <div className="ticket-list">{tickets.map((ticket) => <button key={ticket.id} className={selected?.id === ticket.id ? 'ticket-row active' : 'ticket-row'} onClick={() => setSelectedId(ticket.id)}><div><strong>{ticket.public_code}</strong><span className={`severity ${ticket.severity}`}>{ticket.severity}</span></div><p>{ticket.summary}</p><small>{ticket.status.replace('_', ' ')}</small></button>)}</div>
      </aside>
      <main className="ticket-detail">
        {error && <p className="error-banner" role="alert">{error}</p>}
        {!selected ? <div className="empty-state">当前没有工单。客户确认升级后，工单会出现在这里。</div> : <>
          <div className="ticket-title"><div><p className="eyebrow">{selected.public_code}</p><h1>{selected.summary}</h1></div><span className={`status-pill ${selected.status}`}>{selected.status}</span></div>
          <div className="ticket-meta"><span>{selected.category}</span><span>{selected.severity}</span><span>v{selected.version}</span><span>{new Date(selected.created_at).toLocaleString()}</span></div>
          <section className="detail-card"><h3>问题描述</h3><p>{selected.description}</p></section>
          <section className="detail-card"><h3>诊断上下文</h3><pre>{JSON.stringify(selected.diagnostic_context, null, 2)}</pre></section>
          <section className="detail-card actions-card"><h3>人工处理</h3>
            {!selected.assignee_id && selected.status === 'open' && <button className="primary" disabled={busy} onClick={() => mutate(() => claimTicket(token, selected))}>认领并分诊</button>}
            {selected.assignee_id === user.id && (NEXT_STATUS[selected.status] ?? []).map((status) => <button key={status} className="ghost" disabled={busy} onClick={() => mutate(() => transitionTicket(token, selected, status, `人工处理：转为 ${status}`))}>转为 {status}</button>)}
            {selected.assignee_id && selected.assignee_id !== user.id && <p className="muted">该工单已由其他支持人员认领。</p>}
          </section>
          <section className="detail-card"><h3>状态轨迹</h3>{selected.transitions.length ? <ol className="transition-list">{selected.transitions.map((transition) => <li key={transition.id}><strong>{transition.from_status} → {transition.to_status}</strong><span>{transition.reason}</span></li>)}</ol> : <p className="muted">尚无人工状态变更。</p>}</section>
          {selected.agent_run_id && <FeedbackForm token={token} ticket={selected} />}
        </>}
      </main>
    </div>
  )
}

function FeedbackForm({ token, ticket }: { token: string; ticket: Ticket }) {
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    try {
      await submitFeedback(token, ticket, {
        agent_run_id: ticket.agent_run_id,
        disposition: data.get('disposition'),
        resolution_category: ticket.category,
        knowledge_gap: data.get('knowledge_gap') === 'on',
        comment: data.get('comment') || null,
      })
      setSent(true)
    } catch (caught) { setError(messageFrom(caught)) }
  }
  return <form className="detail-card feedback-form" onSubmit={submit}><h3>反馈回流</h3>{sent ? <p className="success-banner">反馈已记录，可用于后续离线评测。</p> : <><label>Agent 建议<select name="disposition"><option value="accepted">直接采纳</option><option value="edited">修改后采纳</option><option value="rejected">拒绝</option></select></label><label>复盘说明<textarea name="comment" rows={3} /></label><label className="check"><input type="checkbox" name="knowledge_gap" />存在知识缺口</label><button className="primary">提交反馈</button></>}{error && <p className="error-banner">{error}</p>}</form>
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? '')
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [restoring, setRestoring] = useState(Boolean(token))

  useEffect(() => {
    if (!token || user) return
    getCurrentUser(token).then(setUser).catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 401) localStorage.removeItem(TOKEN_KEY)
      setToken('')
    }).finally(() => setRestoring(false))
  }, [token, user])

  if (restoring) return <div className="splash">恢复安全会话…</div>
  if (!token || !user) return <Login onAuthenticated={(nextToken, nextUser) => { setToken(nextToken); setUser(nextUser) }} />
  return <div className="app-shell"><header className="topbar"><div className="brand"><span>SP</span><div><strong>SupportPilot</strong><small>Evidence-led support</small></div></div><div className="user-chip"><div><strong>{user.display_name}</strong><small>{user.role}</small></div><button onClick={() => { localStorage.removeItem(TOKEN_KEY); setToken(''); setUser(null) }}>退出</button></div></header>{user.role === 'support_agent' ? <SupportWorkspace token={token} user={user} /> : <CustomerWorkspace token={token} />}</div>
}
