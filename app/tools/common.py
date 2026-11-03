"""Fronteira única de validação, limites, erros sanitizados e retorno estruturado."""

import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.services.errors import ServiceError
from app.tools.schemas import Arguments, ErrorCode, ToolError, ToolResponse

MAX_ARGUMENT_BYTES = 8192
MAX_RESPONSE_BYTES = 65536
Input = TypeVar("Input", bound=Arguments)
Output = TypeVar("Output", bound=BaseModel)

MESSAGES: dict[ErrorCode, str] = {
    "unknown_tool": "Ferramenta não disponível.",
    "invalid_arguments": "Revise os parâmetros informados.",
    "not_found": "Produto não encontrado.",
    "ambiguous": "Há mais de um produto com esse nome; informe o ID.",
    "unavailable": "Produto indisponível para oferta no snapshot.",
    "invalid_installments": "Parcelamento não elegível para esse valor.",
    "forbidden": "Pedido não encontrado ou sem autorização de acesso.",
    "no_evidence": "Não há evidência suficiente para essa consulta.",
    "service_unavailable": "Não foi possível verificar a informação agora.",
    "response_too_large": "Resultado excede o limite; refine a consulta.",
}


class NoEvidence(ServiceError):
    code = "no_evidence"


def failure(code: ErrorCode, fields: tuple[str, ...] = ()) -> ToolResponse:
    return ToolResponse(
        status="error",
        data=None,
        error=ToolError(code=code, message=MESSAGES[code], invalid_fields=fields),
    )


def run_tool(
    arguments: object,
    input_model: type[Input],
    output_model: type[Output],
    operation: Callable[[Input], object],
) -> ToolResponse[Output]:
    try:
        if type(arguments) is not dict:
            return failure("invalid_arguments")
        encoded = json.dumps(arguments, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_ARGUMENT_BYTES:
            return failure("invalid_arguments")
        params = input_model.model_validate(arguments)
    except ValidationError as exc:
        fields = set()
        for item in exc.errors(include_input=False, include_context=False, include_url=False):
            root = str(item["loc"][0]) if item["loc"] else "$"
            fields.add(root if root in input_model.model_fields else "$")
        return failure("invalid_arguments", tuple(sorted(fields)))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return failure("invalid_arguments")
    try:
        raw = operation(params)
        # Revalidar os dados em vez de confiar no modelo retornado pelo serviço.
        payload = (
            raw.model_dump(mode="python", warnings="error") if isinstance(raw, BaseModel) else raw
        )
        data = output_model.model_validate(payload, strict=True)
        result = ToolResponse[output_model](status="ok", data=data, error=None)
        if len(result.model_dump_json().encode("utf-8")) > MAX_RESPONSE_BYTES:
            return failure("response_too_large")
        return result
    except ServiceError as exc:
        code = (
            exc.code
            if isinstance(exc.code, str) and exc.code in MESSAGES
            else "service_unavailable"
        )
        return failure(code)
    except Exception:
        # A fronteira não expõe traceback, SQL, argumentos, PII ou conteúdo do manual.
        return failure("service_unavailable")
