"""Lista fechada de ferramentas e schemas independentes de SDK/provedor."""

from app.services.models import OrderAccessContext
from app.services.order_service import OrderService
from app.services.policy_service import PolicyService
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService
from app.tools.catalog_mapper import CatalogQueryMapper
from app.tools.common import failure
from app.tools.order_tools import OrderTools
from app.tools.policy_tools import PolicyTools
from app.tools.pricing_tools import PricingTools
from app.tools.product_tools import ProductTools
from app.tools.schemas import (
    RESPONSE_MODELS,
    OrderStatusInput,
    PolicySearchInput,
    ProductDetailsInput,
    ProductOffersInput,
    SearchProductsInput,
    StoreInfoInput,
    ToolResponse,
)

INPUT_MODELS = {
    "search_products": SearchProductsInput,
    "get_product_details": ProductDetailsInput,
    "get_product_offers": ProductOffersInput,
    "get_order_status": OrderStatusInput,
    "search_store_policies": PolicySearchInput,
    "get_store_info": StoreInfoInput,
}
DESCRIPTIONS = {
    "search_products": (
        "Filtra catálogo no snapshot. category deve corresponder ao instrumento pedido "
        "(Ukuleles para ukuleles, Violões para violões). term pesquisa somente o nome/modelo: "
        "ukulele soprano usa category='Ukuleles', term='soprano'. Cor e cordas em specs "
        "(color=natural, strings=nylon); não invente atributos para subtipos presentes no nome. "
        "Preserve todos os filtros."
    ),
    "get_product_details": "Consulta ID ou nome exato, status, estoque e disponibilidade.",
    "get_product_offers": (
        "Consulta ofertas de um produto. Para N parcelas envie payment_method='credit' "
        "e installments=N. Não calcule valores nem substitua um plano rejeitado."
    ),
    "get_order_status": "Consulta pedido com autorização externa do backend; ID não autentica.",
    "search_store_policies": (
        "Consulta regras gerais (inclusive parcelas mínimas, sem exigir produto), "
        "com seção, página e versão. Use top_k=3 salvo pedido de mais referências."
    ),
    "get_store_info": "Consulta endereço, horários ou contatos públicos com fontes e ambiguidades.",
}


def tool_contracts() -> list[dict]:
    """JSON Schemas de entrada e saída; não há definição de SQL ou de identidade."""
    return [
        {
            "name": name,
            "description": DESCRIPTIONS[name],
            "input_schema": model.model_json_schema(mode="validation"),
            "output_schema": RESPONSE_MODELS[name].model_json_schema(mode="serialization"),
        }
        for name, model in INPUT_MODELS.items()
    ]


class ToolRegistry:
    def __init__(
        self,
        products: ProductService,
        pricing: PricingService,
        orders: OrderService,
        policies: PolicyService | None,
    ) -> None:
        self.catalog_mapper = CatalogQueryMapper(products)
        product_tools = ProductTools(products)
        policy_tools = PolicyTools(policies)
        self._handlers = {
            "search_products": product_tools.search_products,
            "get_product_details": product_tools.get_product_details,
            "get_product_offers": PricingTools(pricing).get_product_offers,
            "search_store_policies": policy_tools.search_store_policies,
            "get_store_info": policy_tools.get_store_info,
        }
        self._orders = OrderTools(orders)

    def call(
        self,
        name: str,
        arguments: object,
        *,
        order_access: OrderAccessContext | None = None,
    ) -> ToolResponse:
        if type(name) is not str or len(name) > 64:
            return failure("unknown_tool")
        if name == "get_order_status":
            return self._orders.get_order_status(arguments, access=order_access)
        if name not in self._handlers:
            return failure("unknown_tool")
        return self._handlers[name](arguments)
