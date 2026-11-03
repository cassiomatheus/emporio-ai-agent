"""Loop limitado; contexto não substitui evidência nem autorização do backend."""

import asyncio
import json

from app.agent.catalog_contracts import agent_tool_contracts
from app.agent.memory import ConversationContext
from app.agent.models import (
    AgentLimits,
    AgentRequest,
    AgentResult,
    AnswerPlan,
    FunctionCall,
    ModelTurn,
    SearchPage,
    TokenUsage,
    ToolTrace,
)
from app.agent.pagination import wants_next_page
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.provider import LLMProvider, ProviderError, ProviderTimeout
from app.agent.rendering import render_plan
from app.agent.requirements import (
    asks_payment_terms,
    mentions_cash,
    needs_cash_policy,
    needs_receipt_date,
)
from app.agent.security import accessory_request, redact, refers_to_product, suspicious
from app.schemas.catalog_request import CatalogInterpretation
from app.services.models import OrderAccessContext
from app.tools.catalog_mapper import CatalogClarification
from app.tools.common import MAX_ARGUMENT_BYTES, failure
from app.tools.registry import ToolRegistry, tool_contracts
from app.tools.schemas import RESPONSE_MODELS, SearchProductsInput, ToolResponse

SAFE_MESSAGE = (
    "Não consegui confirmar essa informação nas fontes agora. "
    "Pode tentar novamente ou pedir ajuda a um atendente da loja?"
)
ACCESS_DENIED_MESSAGE = (
    "Acesso negado: não posso consultar esse pedido sem a autorização necessária. "
    "Um atendente pode ajudar a confirmar o acesso."
)
UNCONFIRMED_PAYMENT_MESSAGE = (
    "Não consegui confirmar nas fontes disponíveis as condições para essa forma de pagamento. "
    "Confirme com um atendente da loja antes de contar com um desconto."
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("invalid_json_constant")


def _arguments(call: FunctionCall) -> object:
    if len(call.arguments.encode("utf-8")) > MAX_ARGUMENT_BYTES:
        raise ValueError("arguments_too_large")
    return json.loads(
        call.arguments, object_pairs_hook=_unique_object, parse_constant=_reject_constant
    )


class AgentOrchestrator:
    def __init__(
        self, provider: LLMProvider, tools: ToolRegistry, limits: AgentLimits | None = None
    ) -> None:
        self.provider = provider
        self.tools = tools
        self.limits = limits or AgentLimits()
        self.catalog_mapper = getattr(tools, "catalog_mapper", None)

    def _execute_tool(
        self,
        name: str,
        arguments: object,
        message: str,
        access: OrderAccessContext | None,
        interpret_catalog: bool,
    ) -> tuple[ToolResponse, CatalogInterpretation | None, object]:
        interpretation = None
        if name == "search_products" and self.catalog_mapper is not None and interpret_catalog:
            interpretation = self.catalog_mapper.prepare(arguments, message)
            arguments = interpretation.query.model_dump(mode="json")
        response = self.tools.call(name, arguments, order_access=access)
        return response, interpretation, arguments

    async def run(
        self,
        request: AgentRequest,
        *,
        order_access: OrderAccessContext | None = None,
        conversation: ConversationContext | None = None,
    ) -> AgentResult:
        # Evidências nunca atravessam turnos, mesmo quando há contexto conversacional.
        traces: list[ToolTrace] = []
        usage: list[TokenUsage] = []
        rounds = 0
        evidence: dict[str, tuple[str, ToolResponse]] = {}
        reference_ids: tuple[int, ...] | None = None
        search_page: SearchPage | None = None
        search_queries: dict[str, SearchProductsInput] = {}
        cash_policy_only = needs_cash_policy(request.message)
        interpretations: list[CatalogInterpretation] = []

        def result(status: str, text: str = SAFE_MESSAGE) -> AgentResult:
            totals = (
                TokenUsage(
                    input_tokens=sum(item.input_tokens for item in usage),
                    output_tokens=sum(item.output_tokens for item in usage),
                    total_tokens=sum(item.total_tokens for item in usage),
                )
                if usage
                else None
            )
            return AgentResult(
                status=status,
                text=text,
                rounds=rounds,
                tools=tuple(traces),
                usage=totals,
                reference_ids=reference_ids,
                search_page=search_page,
                catalog_interpretations=tuple(interpretations),
            )

        def finish_plan(plan: AnswerPlan) -> AgentResult:
            nonlocal reference_ids, search_page
            if (
                cash_policy_only
                and plan.intent != "answer"
                or (plan.intent == "out_of_scope" and asks_payment_terms(request.message))
            ):
                return result("answered", UNCONFIRMED_PAYMENT_MESSAGE)
            try:
                text = render_plan(plan, evidence)
                ids: list[int] = []
                product_query = False
                for call_id in plan.evidence_call_ids:
                    name, response = evidence[call_id]
                    if name == "search_products":
                        product_query = True
                        ids.extend(item.product_id for item in response.data.items)
                    elif name in ("get_product_details", "get_product_offers"):
                        product_query = True
                        ids.append(response.data.product_id)
                if product_query:
                    unique = tuple(dict.fromkeys(ids))
                    reference_ids = unique if len(unique) <= 20 else ()
                if len(plan.evidence_call_ids) == 1:
                    call_id = plan.evidence_call_ids[0]
                    if call_id in search_queries:
                        search_page = SearchPage(
                            query=search_queries[call_id],
                            returned_count=len(evidence[call_id][1].data.items),
                        )
                return result("answered", text)
            except (ValueError, TypeError, KeyError):
                return result("abstained")

        if not request.message.strip():
            return result("abstained")
        if suspicious(request.message):
            return result("abstained", render_plan(AnswerPlan(intent="handoff"), {}))
        if accessory_request(request.message):
            return result("answered", render_plan(AnswerPlan(intent="out_of_scope"), {}))
        if needs_receipt_date(request.message):
            return result(
                "answered",
                render_plan(AnswerPlan(intent="clarify", clarification="receipt_date"), {}),
            )
        continuation_query = None
        if wants_next_page(request.message):
            if conversation is None or conversation.search_page is None:
                return result(
                    "answered",
                    "Qual busca de produtos você quer continuar? Faça uma busca por vez "
                    "para que eu possa mostrar as próximas opções.",
                )
            search_page = conversation.search_page
            try:
                continuation_query = SearchProductsInput.model_validate(
                    {
                        **search_page.query.model_dump(mode="json"),
                        "offset": search_page.next_offset,
                    }
                )
            except ValueError:
                return result(
                    "answered", "O limite de paginação foi atingido. Refine os filtros da busca."
                )
        reference_id = None
        if conversation is not None and refers_to_product(request.message):
            if len(conversation.reference.product_ids) != 1:
                return result(
                    "answered",
                    render_plan(AnswerPlan(intent="clarify", clarification="product"), {}),
                )
            reference_id = conversation.reference.product_ids[0]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation is not None:
            for user, assistant in conversation.history:
                messages.extend(
                    (
                        {"role": "user", "content": redact(user)},
                        {"role": "assistant", "content": redact(assistant)},
                    )
                )
        if reference_id is not None:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"Referência fornecida pelo backend: product_id={reference_id}. "
                        "Para este seguimento consulte detalhes/ofertas por esse ID."
                    ),
                }
            )
        messages.append({"role": "user", "content": redact(request.message)})
        contracts = [
            contract
            for contract in (
                agent_tool_contracts() if self.catalog_mapper is not None else tool_contracts()
            )
            if not cash_policy_only or contract["name"] == "search_store_policies"
        ]
        try:
            async with asyncio.timeout(self.limits.timeout_seconds):
                for round_number in range(1, self.limits.max_rounds + 1):
                    rounds = round_number
                    if len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > 131072:
                        return result("protocol_error")
                    if continuation_query is not None:
                        # Decisão do backend: reutiliza a mesma execução validada de tools.
                        # Não há chamada nem resposta simulada do provedor neste caminho.
                        turn = ModelTurn(
                            calls=(
                                FunctionCall(
                                    call_id="next_catalog_page",
                                    name="search_products",
                                    arguments=continuation_query.model_dump_json(),
                                ),
                            )
                        )
                    else:
                        turn = await asyncio.wait_for(
                            self.provider.complete(
                                messages,
                                contracts,
                                timeout=self.limits.request_timeout_seconds,
                                max_output_tokens=self.limits.max_output_tokens,
                            ),
                            timeout=self.limits.request_timeout_seconds,
                        )
                    if turn.usage is not None:
                        usage.append(turn.usage)
                    if not turn.calls:
                        try:
                            parsed = json.loads(
                                turn.final_text or "",
                                object_pairs_hook=_unique_object,
                                parse_constant=_reject_constant,
                            )
                            plan = AnswerPlan.model_validate(parsed)
                            return finish_plan(plan)
                        except (ValueError, TypeError, KeyError):
                            return result("abstained")
                    if (
                        len(turn.calls) > self.limits.max_calls_per_round
                        or len(traces) + len(turn.calls) > self.limits.max_tool_calls
                    ):
                        return result("call_limit")
                    ids = [call.call_id for call in turn.calls]
                    if len(ids) != len(set(ids)) or any(call_id in evidence for call_id in ids):
                        return result("protocol_error")
                    output = turn.output_items or tuple(
                        {
                            "type": "function_call",
                            "call_id": call.call_id,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                        for call in turn.calls
                    )
                    messages.extend(output)
                    for call in turn.calls:
                        trace_name = call.name if call.name in RESPONSE_MODELS else "unknown_tool"
                        try:
                            arguments = _arguments(call)
                            if cash_policy_only and call.name != "search_store_policies":
                                raise ValueError("payment_method_requires_policy")
                            if reference_id is not None and (
                                call.name == "search_products"
                                or call.name in ("get_product_details", "get_product_offers")
                                and (
                                    not isinstance(arguments, dict)
                                    or arguments.get("product_id") != reference_id
                                )
                            ):
                                raise ValueError("reference_mismatch")
                        except (ValueError, UnicodeError, RecursionError):
                            response = failure("invalid_arguments")
                        else:
                            try:
                                (
                                    response,
                                    interpretation,
                                    prepared_arguments,
                                ) = await asyncio.wait_for(
                                    asyncio.to_thread(
                                        self._execute_tool,
                                        call.name,
                                        arguments,
                                        request.message,
                                        order_access,
                                        continuation_query is None,
                                    ),
                                    timeout=self.limits.tool_timeout_seconds,
                                )
                                if interpretation is not None:
                                    interpretations.append(interpretation)
                                if call.name in RESPONSE_MODELS:
                                    response = RESPONSE_MODELS[call.name].model_validate_json(
                                        response.model_dump_json(warnings="error"),
                                    )
                                if response.status == "ok" and suspicious(
                                    response.model_dump_json(warnings="error")
                                ):
                                    response = failure("service_unavailable")
                                if (
                                    cash_policy_only
                                    and response.status == "ok"
                                    and not any(
                                        mentions_cash(hit.excerpt) for hit in response.data.hits
                                    )
                                ):
                                    # Um trecho sobre PIX não comprova uma regra para dinheiro.
                                    response = failure("no_evidence")
                                if call.name == "search_products" and response.status == "ok":
                                    search_queries[call.call_id] = (
                                        SearchProductsInput.model_validate(
                                            prepared_arguments
                                        ).model_copy(deep=True)
                                    )
                            except CatalogClarification as exc:
                                traces.append(
                                    ToolTrace(
                                        call_id=call.call_id,
                                        name=trace_name,
                                        status="error",
                                        error_code="invalid_arguments",
                                    )
                                )
                                return result(
                                    "answered",
                                    render_plan(
                                        AnswerPlan(intent="clarify", clarification=exc.kind), {}
                                    ),
                                )
                            except TimeoutError:
                                traces.append(
                                    ToolTrace(
                                        call_id=call.call_id,
                                        name=trace_name,
                                        status="error",
                                        error_code="timeout",
                                    )
                                )
                                return result("timeout")
                            except Exception:
                                response = failure("service_unavailable")
                        evidence[call.call_id] = (call.name, response)
                        traces.append(
                            ToolTrace(
                                call_id=call.call_id,
                                name=trace_name,
                                status=response.status,
                                error_code=response.error.code if response.error else None,
                            )
                        )
                        if (
                            call.name == "get_order_status"
                            and response.error is not None
                            and response.error.code == "forbidden"
                        ):
                            # Negativa é uma decisão do backend, não uma intenção do modelo.
                            return result("answered", ACCESS_DENIED_MESSAGE)
                        if cash_policy_only and response.error is not None:
                            return result("answered", UNCONFIRMED_PAYMENT_MESSAGE)
                        if response.error is not None and (
                            response.error.code
                            in {
                                "unknown_tool",
                                "service_unavailable",
                                "not_found",
                                "unavailable",
                                "invalid_installments",
                                "no_evidence",
                            }
                            or call.name == "get_order_status"
                            and response.error.code == "invalid_arguments"
                        ):
                            # Falhas de fonte/protocolo e condições rejeitadas não permitem
                            # substituir a solicitação nem divulgar evidências parciais.
                            return result("answered", render_plan(AnswerPlan(intent="handoff"), {}))
                        messages.append(
                            {
                                "type": "function_call_output",
                                "call_id": call.call_id,
                                "output": response.model_dump_json(warnings="error"),
                            }
                        )
                    if continuation_query is not None:
                        return finish_plan(
                            AnswerPlan(intent="answer", evidence_call_ids=(turn.calls[0].call_id,))
                        )
                return result("round_limit")
        except (TimeoutError, ProviderTimeout):
            return result("timeout")
        except ProviderError:
            return result("provider_error")
        except Exception:
            return result("protocol_error")
