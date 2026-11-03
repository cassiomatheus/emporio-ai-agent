"""Parcelas completas, valores verificados e busca única sem rodapé de páginas."""

import re
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.agent.models import AnswerPlan
from app.agent.rendering import render_plan
from app.database.repository import PricingRepository, ProductRepository
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService
from app.tools.pricing_tools import PricingTools
from app.tools.product_tools import ProductTools


def payment_response(product, cents, installments):
    repository = Mock(spec=PricingRepository)
    repository.get_pricing_data.return_value = (replace(product, price_cents=cents), ())
    return PricingTools(PricingService(repository)).get_product_offers(
        {
            "product_id": product.product_id,
            "payment_method": "credit",
            "installments": installments,
        }
    )


def render(name, response):
    return render_plan(
        AnswerPlan(intent="answer", evidence_call_ids=("verified",)),
        {"verified": (name, response)},
    )


@pytest.mark.parametrize("installments", [1, 12])
def test_table_keeps_every_eligible_plan_even_with_a_selected_plan(product, installments):
    response = payment_response(product, 459900, installments)
    text = render("get_product_offers", response)
    assert "Parcelamento sem juros: até 12x." in text
    assert "| Parcelas | Valor de cada parcela |" in text
    assert [int(n) for n in re.findall(r"^\| (\d+)x \|", text, re.MULTILINE)] == list(range(1, 13))
    assert "| 12x | R$ 383,25 |" in text
    assert "R$ 383,25, R$ 383,25" not in text
    assert f"Plano de {installments}x:" in text
    assert response.data.selected_plan.total_brl == Decimal("4599.00")
    if installments == 12:
        assert "Plano de 12x: 12 × R$ 383,25; total R$ 4.599,00." in text


def test_table_does_not_offer_installments_below_minimum(product):
    response = payment_response(product, 32310, 4)
    text = render("get_product_offers", response)
    assert "até 4x" in text and "| 5x |" not in text
    assert [int(n) for n in re.findall(r"^\| (\d+)x \|", text, re.MULTILINE)] == [1, 2, 3, 4]


def test_cent_adjustments_are_explicit_and_selected_plan_has_exact_grouped_values(product):
    response = payment_response(product, 329900, 7)
    text = render("get_product_offers", response)
    assert "| 7x | R$ 471,28 a R$ 471,29 |" in text
    assert "intervalos indicam ajuste de centavos" in text
    assert "Plano de 7x: 4 × R$ 471,29 + 3 × R$ 471,28; total R$ 3.299,00." in text
    assert sum(response.data.selected_plan.amounts) == Decimal("3299.00")


@pytest.mark.parametrize("count", [1, 2])
def test_single_page_search_has_no_pagination_notice(product, count):
    repository = Mock(spec=ProductRepository)
    repository.list_products.return_value = [
        replace(product, product_id=100 + i) for i in range(count)
    ]
    response = ProductTools(ProductService(repository)).search_products({})
    text = render("search_products", response)
    assert product.name in text
    assert "Mostrando" not in text and "última página" not in text and "continuar" not in text
    if count == 1:
        assert "Encontrei este instrumento" in text


def test_last_page_with_one_item_still_has_pagination_notice(product):
    repository = Mock(spec=ProductRepository)
    repository.list_products.return_value = [
        replace(product, product_id=100 + i) for i in range(11)
    ]
    response = ProductTools(ProductService(repository)).search_products({"offset": 10})
    text = render("search_products", response)
    assert "Mostrando 11 a 11 de 11 resultados." in text and "última página" in text
