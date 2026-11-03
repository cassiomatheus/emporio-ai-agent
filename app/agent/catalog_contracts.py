"""Contrato do agente: intenção semântica para a mesma tool executável de catálogo."""

from app.schemas.catalog_request import CatalogSearchRequest
from app.tools.registry import tool_contracts


def _inline_refs(value: object, definitions: dict) -> object:
    if isinstance(value, list):
        return [_inline_refs(item, definitions) for item in value]
    if isinstance(value, dict):
        if "$ref" in value:
            return _inline_refs(definitions[value["$ref"].rsplit("/", 1)[1]], definitions)
        return {key: _inline_refs(item, definitions) for key, item in value.items()}
    return value


def agent_tool_contracts() -> list[dict]:
    contracts = tool_contracts()
    for contract in contracts:
        if contract["name"] == "search_products":
            schema = CatalogSearchRequest.model_json_schema(mode="validation")
            # A operação já é determinada pelo nome da função. Evitar confundir
            # esse campo redundante com o intent do plano final da conversa.
            schema["properties"].pop("intent")
            definitions = schema.pop("$defs", {})

            contract["input_schema"] = _inline_refs(schema, definitions)
            contract["description"] = (
                "Busca produtos a partir de um pedido estruturado. Extraia product.category "
                "como o tipo pedido pelo cliente, product.subtype como a variante, product.name "
                "somente para marca/modelo. characteristics recebe cor, cordas e demais "
                "características pedidas; min_price/max_price preservam o orçamento em reais. "
                "O backend normaliza categorias e atributos contra o catálogo. "
                "Use o objeto product obrigatório, sem espalhar category/subtype na raiz. "
                'Formato: {"product":{"category":"tipo de instrumento","subtype":null,'
                '"name":null},"characteristics":{},"max_price":null}. '
                "Não gere category_id, term, specs, SQL ou identidade do cliente."
            )
    return contracts
