# SupportPilot 系统架构

## 组件视图

```mermaid
flowchart LR
    C[客户] --> UI[React Console]
    S[支持人员] --> UI
    UI -->|JWT + REST/SSE| API[FastAPI modular monolith]
    API --> AUTH[Auth / RBAC]
    API --> AGENT[LangGraph Agent]
    AGENT --> SAFE[Risk & Injection Gate]
    AGENT --> RAG[Hybrid RAG]
    AGENT --> TOOLS[Deterministic business tools]
    AGENT --> TICKET[Ticket workflow]
    RAG --> PG[(PostgreSQL + pgvector)]
    TOOLS --> PG
    TICKET --> PG
    AUTH --> PG
    AGENT --> LLM[DecisionProvider: deterministic / Qwen]
    API -. spans .-> OTLP[OTLP Collector optional]
```

## 核心数据闭环

```mermaid
sequenceDiagram
    participant U as Customer UI
    participant A as FastAPI / AgentService
    participant G as LangGraph
    participant D as PostgreSQL
    participant H as Support UI
    U->>A: POST resolve/stream + JWT
    A->>D: lock/load conversation
    A->>G: stream(initial_state)
    loop each completed node
        G-->>A: state + TraceEvent
        A-->>U: SSE progress
    end
    A->>D: AgentRun + conversation + audit, commit
    A-->>U: SSE result
    opt needs confirmation
        U->>A: confirm + Idempotency-Key
        A->>D: create one Ticket
        H->>A: claim/transition + version + key
        A->>D: TicketTransition + audit
        H->>A: feedback linked to AgentRun
        A->>D: HumanFeedback
    end
```

## 关键不变量

- LLM 只给出结构化意图，不计算额度、不判断权限、不直接执行高风险动作；
- 知识回答必须通过 Answerability Gate 并带 chunk 级引用；
- 写操作同时使用事务、幂等键、唯一约束和版本检查；
- 高风险请求直接拒绝并审计，Prompt Injection 在模型/工具之前预检；
- 最终 SSE result 在数据库 commit 后发送。
