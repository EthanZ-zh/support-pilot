param(
    [string]$ApiBase = 'http://127.0.0.1:8000/api/v1',
    [string]$DemoPassword = 'SupportPilotDemo!2026'
)

$ErrorActionPreference = 'Stop'

function Login-DemoUser([string]$Email) {
    return Invoke-RestMethod -Method Post -Uri "$ApiBase/auth/login" -ContentType 'application/json' -Body (@{
        email = $Email
        password = $DemoPassword
    } | ConvertTo-Json)
}

function Invoke-Agent([string]$Token, [hashtable]$Payload, [string]$IdempotencyKey = '') {
    $headers = @{ Authorization = "Bearer $Token" }
    if ($IdempotencyKey) { $headers['Idempotency-Key'] = $IdempotencyKey }
    return Invoke-RestMethod -Method Post -Uri "$ApiBase/agent/resolve" -Headers $headers -ContentType 'application/json' -Body ($Payload | ConvertTo-Json -Depth 6)
}

$customer = Login-DemoUser 'alpha.admin@example.com'
$sessionId = [Guid]::NewGuid().ToString()
$answer = Invoke-Agent $customer.access_token @{
    session_id = $sessionId
    message = 'HTTP 429 响应里的 Retry-After 应该如何处理？'
}
if ($answer.outcome -ne 'answered' -or $answer.citations.Count -lt 1) {
    throw 'Knowledge answer did not include a successful cited response.'
}

$ticketSessionId = [Guid]::NewGuid().ToString()
$draft = Invoke-Agent $customer.access_token @{
    session_id = $ticketSessionId
    message = '这个问题仍未解决，请创建工单转人工。'
}
if ($draft.outcome -ne 'needs_confirmation') { throw 'Agent did not request ticket confirmation.' }

$created = Invoke-Agent $customer.access_token @{
    session_id = $ticketSessionId
    message = '确认创建工单'
    confirmation = 'confirm_ticket'
} "demo-confirm-$ticketSessionId"
if ($created.outcome -ne 'escalated') { throw 'Confirmed ticket was not created.' }

$support = Login-DemoUser 'support.agent@example.com'
$supportHeaders = @{ Authorization = "Bearer $($support.access_token)" }
$ticketId = [string]$created.tool_result.ticket_id
$ticket = Invoke-RestMethod -Method Get -Uri "$ApiBase/tickets/$ticketId" -Headers $supportHeaders
$claimed = Invoke-RestMethod -Method Post -Uri "$ApiBase/tickets/$ticketId/claim" -Headers ($supportHeaders + @{ 'Idempotency-Key' = "demo-claim-$ticketId" }) -ContentType 'application/json' -Body (@{ expected_version = $ticket.version } | ConvertTo-Json)
$progressed = Invoke-RestMethod -Method Post -Uri "$ApiBase/tickets/$ticketId/transitions" -Headers ($supportHeaders + @{ 'Idempotency-Key' = "demo-progress-$ticketId" }) -ContentType 'application/json' -Body (@{ to_status = 'in_progress'; expected_version = $claimed.version; reason = 'Demo support agent started investigation.' } | ConvertTo-Json)

[pscustomobject]@{
    knowledge_outcome = $answer.outcome
    citation_count = $answer.citations.Count
    ticket_code = $progressed.public_code
    ticket_status = $progressed.status
    trace_id = $created.trace_id
} | Format-List
