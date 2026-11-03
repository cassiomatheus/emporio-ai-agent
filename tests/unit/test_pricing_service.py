"""Ofertas não cumulativas, valores exatos e limites de parcelas sem SQLite."""

from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.database.repository import (
    PricingRepository,
    ProductRecord,
    PromotionRecord,
    RepositoryError,
)
from app.services.errors import (
    InvalidInstallments,
    ProductNotFound,
    ProductUnavailable,
    ServiceUnavailable,
)
from app.services.models import QuoteRequest
from app.services.pricing_service import PricingService, installment_plans


def make_service(product: ProductRecord, promotions: tuple = ()) -> PricingService:
    repository = Mock(spec=PricingRepository)
    repository.get_pricing_data.return_value = (product, promotions)
    return PricingService(repository)


def test_kalani_127_promotion_and_pix_do_not_stack(product: ProductRecord) -> None:
    service = make_service(
        replace(product, product_id=127, price_cents=35900),
        (
            PromotionRecord(12, 127, 10, 1),
            PromotionRecord(13, 127, 50, 0),
        ),
    )
    for method in ("pix", "credit", "debit", "boleto"):
        quote = service.quote(QuoteRequest(product_id=127, payment_method=method))
        assert quote.original_price == Decimal("359.00")
        assert quote.discount_percent == Decimal(10)
        assert quote.final_price == Decimal("323.10")
        assert quote.discount_source == "promotion"
        assert quote.promotion_id == 12
    with pytest.raises(InvalidInstallments):
        service.quote(QuoteRequest(product_id=127, payment_method="credit", installments=6))


def test_inactive_offer_and_pix_on_list_price(product: ProductRecord) -> None:
    service = make_service(replace(product, price_cents=100000), (PromotionRecord(1, 81, 50, 0),))
    pix = service.quote(QuoteRequest(product_id=81, payment_method="pix"))
    credit = service.quote(QuoteRequest(product_id=81, payment_method="credit"))
    assert pix.final_price == Decimal("950.00")
    assert pix.discount_percent == 5
    assert pix.discount_source == "pix"
    assert pix.promotion_id is None
    assert credit.final_price == Decimal("1000.00")
    assert credit.discount_source == "none"


def test_best_single_discount_with_deterministic_ties(product: ProductRecord) -> None:
    service = make_service(
        replace(product, price_cents=10000),
        (
            PromotionRecord(5, 81, 20, 1),
            PromotionRecord(2, 81, 20, 1),
            PromotionRecord(1, 81, 10, 1),
            PromotionRecord(3, 999, 99, 1),
        ),
    )
    quote = service.quote(QuoteRequest(product_id=81, payment_method="pix"))
    assert quote.final_price == Decimal("80.00")
    assert quote.discount_percent == 20
    assert quote.promotion_id == 2
    smaller = make_service(product, (PromotionRecord(1, 81, 3, 1),))
    assert smaller.quote(QuoteRequest(product_id=81, payment_method="pix")).discount_percent == 5


@pytest.mark.parametrize(
    "total_cents,counts",
    [
        (4999, (1,)),
        (5000, (1,)),
        (9999, (1,)),
        (10000, (1, 2)),
        (14999, (1, 2)),
        (15000, (1, 2, 3)),
        (31999, (1, 2, 3)),
        (32000, (1, 2, 3, 4)),
        (47999, (1, 2, 3, 4, 5)),
        (48000, tuple(range(1, 7))),
        (69999, tuple(range(1, 7))),
        (70000, tuple(range(1, 8))),
        (119999, tuple(range(1, 12))),
        (120000, tuple(range(1, 13))),
    ],
)
def test_installment_minimum_boundaries(total_cents: int, counts: tuple[int, ...]) -> None:
    total = Decimal(total_cents) / 100
    plans = installment_plans(total)
    assert tuple(plan.count for plan in plans) == counts
    for plan in plans:
        assert sum(plan.amounts) == total
        assert min(plan.amounts) >= plan.minimum_brl
        assert max(plan.amounts) - min(plan.amounts) <= Decimal("0.01")
        assert len(plan.amounts) == plan.count
        assert plan.interest_percent == 0


def test_round_half_up_and_exact_distribution(product: ProductRecord) -> None:
    service = make_service(replace(product, price_cents=30))
    assert service.quote(QuoteRequest(product_id=81, payment_method="pix")).final_price == Decimal(
        "0.29"
    )
    plan = next(item for item in installment_plans(Decimal("1000.01")) if item.count == 3)
    assert plan.amounts == (Decimal("333.34"), Decimal("333.34"), Decimal("333.33"))
    assert sum(plan.amounts) == Decimal("1000.01")
    with localcontext() as context:
        context.prec = 3
        low_context_plans = installment_plans(Decimal("1000.01"))
    assert low_context_plans == installment_plans(Decimal("1000.01"))


def test_minimum_uses_discounted_total(product: ProductRecord) -> None:
    service = make_service(replace(product, price_cents=48000), (PromotionRecord(1, 81, 10, 1),))
    with pytest.raises(InvalidInstallments):
        service.quote(QuoteRequest(product_id=81, payment_method="credit", installments=6))
    quote = service.quote(QuoteRequest(product_id=81, payment_method="credit", installments=5))
    assert quote.final_price == Decimal("432.00")
    assert sum(quote.selected_plan.amounts) == quote.final_price


@pytest.mark.parametrize("status,stock", [("discontinued", 13), ("coming_soon", 2), ("active", 0)])
def test_no_offer_for_unavailable_products(product: ProductRecord, status: str, stock: int) -> None:
    with pytest.raises(ProductUnavailable):
        make_service(replace(product, status=status, stock_quantity=stock)).get_offers(81)


@pytest.mark.parametrize("method,count", [("credit", 0), ("credit", 13), ("pix", 2)])
def test_invalid_installment_requests(method: str, count: int) -> None:
    with pytest.raises(ValidationError):
        QuoteRequest(product_id=81, payment_method=method, installments=count)


def test_not_found_and_repository_failure() -> None:
    repository = Mock(spec=PricingRepository)
    repository.get_pricing_data.return_value = None
    with pytest.raises(ProductNotFound):
        PricingService(repository).get_offers(81)
    repository.get_pricing_data.side_effect = RepositoryError("private")
    with pytest.raises(ServiceUnavailable, match="^service_unavailable$"):
        PricingService(repository).get_offers(81)
