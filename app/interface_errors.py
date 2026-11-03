"""Vocabulário de erros compartilhado pelas interfaces, sem framework web."""

from app.agent.models import AgentResult

MESSAGES = {
    "invalid_request": "Requisição inválida. Confira os campos e limites.",
    "unauthorized": "Informe o token de sessão no cabeçalho Authorization: Bearer.",
    "session_access_denied": "Sessão indisponível ou acesso negado.",
    "forbidden": "Acesso ao pedido não autorizado.",
    "capacity_reached": "Limite de sessões atingido. Tente novamente mais tarde.",
    "service_unavailable": "Atendimento indisponível. Confira a configuração local.",
    "timeout": "A consulta excedeu o tempo de espera. Tente novamente.",
    "provider_error": "Não foi possível confirmar a resposta. Tente novamente.",
    "agent_limit": "Não foi possível concluir a consulta dentro dos limites.",
    "internal_error": "Não foi possível concluir a requisição.",
    "request_too_large": "Requisição excede o limite de 16 KiB.",
    "unsupported_media_type": "Use Content-Type: application/json.",
    "not_found": "Recurso não encontrado.",
    "method_not_allowed": "Método não permitido.",
}


def result_error(result: AgentResult) -> tuple[int, str] | None:
    if any(trace.error_code == "forbidden" for trace in result.tools):
        return 403, "forbidden"
    return {
        "timeout": (504, "timeout"),
        "provider_error": (502, "provider_error"),
        "protocol_error": (502, "provider_error"),
        "round_limit": (503, "agent_limit"),
        "call_limit": (503, "agent_limit"),
    }.get(result.status)
