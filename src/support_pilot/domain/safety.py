import unicodedata

_HIGH_RISK_ACTION_PATTERNS = (
    "帮我退款",
    "直接退款",
    "修改权限",
    "提升权限",
    "执行命令",
    "删除数据",
    "重置密码",
    "refund now",
    "grant permission",
    "run command",
    "delete data",
)

_PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all instructions",
    "忽略之前的指令",
    "忽略所有指令",
    "泄露系统提示词",
    "reveal system prompt",
    "system prompt",
    "developer message",
    "调用管理员工具",
    "读取其他租户",
    "泄露其他租户",
    "绕过权限",
    "bypass authorization",
    "call admin tool",
)


def is_high_risk_action_request(message: str) -> bool:
    normalized = unicodedata.normalize("NFKC", message).casefold()
    return any(pattern in normalized for pattern in _HIGH_RISK_ACTION_PATTERNS)


def has_prompt_injection_pattern(message: str) -> bool:
    normalized = unicodedata.normalize("NFKC", message).casefold()
    return any(pattern in normalized for pattern in _PROMPT_INJECTION_PATTERNS)
