"""Ofertas não cumulativas e parcelas elegíveis calculadas sem LLM."""

from decimal import Decimal, localcontext

from pydantic import TypeAdapter

from app.database.repository import PricingRepository, RepositoryError
from app.services.errors import (
    InvalidInstallments,
    ProductNotFound,
    ProductUnavailable,
    ServiceUnavailable,
)
from app.services.models import (
    ID_ADAPTER,
    InstallmentPlan,
    Money,
    PaymentOffer,
    PriceQuote,
    ProductOffers,
    QuoteRequest,
)
from app.services.money import discounted, from_cents
from app.services.product_service import is_available

MONEY_ADAPTER = TypeAdapter(Money)


def installment_plans(total: Decimal) -> tuple[InstallmentPlan, ...]:
    """Seção 3.1: piso conservador de R$ 50 em 2–3x; 1x é à vista."""
    total = MONEY_ADAPTER.validate_python(total)
    with localcontext() as context:
        context.prec = 40
        total_cents = int(total * 100)
    plans = []
    for count in range(1, 13):
        minimum_cents = 0 if count == 1 else 5000 if count <= 3 else 8000 if count <= 6 else 10000
        floor, remainder = divmod(total_cents, count)
        if floor < minimum_cents:
            continue
        amounts = tuple(from_cents(floor + (index < remainder)) for index in range(count))
        plans.append(
            InstallmentPlan(
                count=count,
                amounts=amounts,
                total_brl=total,
                minimum_brl=from_cents(minimum_cents),
            )
        )
    return tuple(plans)


class PricingService:
    def __init__(self, repository: PricingRepository) -> None:
        self.repository = repository

    def get_offers(self, product_id: int) -> ProductOffers:
        product_id = ID_ADAPTER.validate_python(product_id)
        try:
            data = self.repository.get_pricing_data(product_id)
        except RepositoryError as exc:
            raise ServiceUnavailable() from exc
        if data is None:
            raise ProductNotFound()
        product, promotions = data
        if not is_available(product):
            raise ProductUnavailable()
        active = [
            promotion
            for promotion in promotions
            if promotion.is_active == 1 and promotion.product_id == product_id
        ]
        # Escolhe uma única promoção; nenhuma combinação de percentuais.
        promotion = (
            min(active, key=lambda item: (-item.discount_percent, item.promotion_id))
            if active
            else None
        )
        original = from_cents(product.price_cents)
        options = []
        for method in ("pix", "credit", "debit", "boleto"):
            percent = Decimal(promotion.discount_percent) if promotion else Decimal(0)
            source = "promotion" if promotion else "none"
            promotion_id = promotion.promotion_id if promotion else None
            if method == "pix" and percent < 5:
                percent, source, promotion_id = Decimal(5), "pix", None
            final = discounted(original, percent)
            options.append(
                PaymentOffer(
                    payment_method=method,
                    discount_percent=percent,
                    final_price=final,
                    discount_source=source,
                    promotion_id=promotion_id,
                    eligible_installments=installment_plans(final) if method == "credit" else (),
                )
            )
        return ProductOffers(product_id=product_id, original_price=original, options=tuple(options))

    def quote(self, request: QuoteRequest) -> PriceQuote:
        offers = self.get_offers(request.product_id)
        option = next(
            item for item in offers.options if item.payment_method == request.payment_method
        )
        plan = None
        if request.payment_method == "credit":
            plan = next(
                (
                    item
                    for item in option.eligible_installments
                    if item.count == request.installments
                ),
                None,
            )
            if plan is None:
                raise InvalidInstallments()
        return PriceQuote(
            **option.model_dump(),
            product_id=offers.product_id,
            original_price=offers.original_price,
            selected_plan=plan,
        )
