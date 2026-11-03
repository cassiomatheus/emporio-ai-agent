"""Tool de ofertas preserva cálculos, descontos e condições do PricingService."""

from app.services.errors import ServiceUnavailable
from app.services.models import PaymentOffer, QuoteRequest
from app.services.pricing_service import PricingService
from app.tools.common import run_tool
from app.tools.schemas import ProductOffersData, ProductOffersInput, ToolResponse


class PricingTools:
    def __init__(self, service: PricingService) -> None:
        self.service = service

    def get_product_offers(self, arguments: object) -> ToolResponse[ProductOffersData]:
        def operation(params: ProductOffersInput) -> ProductOffersData:
            if params.payment_method is None:
                offers = self.service.get_offers(params.product_id)
                if offers.product_id != params.product_id:
                    raise ServiceUnavailable()
                return ProductOffersData(**offers.model_dump(warnings="error"))
            quote = self.service.quote(
                QuoteRequest(
                    product_id=params.product_id,
                    payment_method=params.payment_method,
                    installments=params.installments or 1,
                )
            )
            if (
                quote.product_id != params.product_id
                or quote.payment_method != params.payment_method
            ):
                raise ServiceUnavailable()
            option = PaymentOffer.model_validate(
                quote.model_dump(
                    warnings="error",
                    exclude={
                        "product_id",
                        "original_price",
                        "selected_plan",
                    },
                )
            )
            return ProductOffersData(
                product_id=quote.product_id,
                original_price=quote.original_price,
                options=(option,),
                selected_plan=quote.selected_plan,
            )

        return run_tool(arguments, ProductOffersInput, ProductOffersData, operation)
