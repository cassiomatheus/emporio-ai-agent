"""Autorização anterior à consulta e ausência de informações fabricadas."""

from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.database.repository import OrderItemRecord, OrderRecord, OrderRepository, RepositoryError
from app.services.errors import OrderAccessDenied, ServiceUnavailable
from app.services.models import OrderAccessContext
from app.services.order_service import OrderService


@pytest.fixture
def order() -> OrderRecord:
    return OrderRecord(
        order_id=3,
        customer_id=7,
        order_date="2026-01-02",
        status="delivered",
        total_cents=345000,
        payment_method="credit_3x",
        tracking_code=None,
        estimated_delivery=None,
        items=(OrderItemRecord(81, "Instrumento sintético", 2),),
    )


@pytest.mark.parametrize("access", [None, OrderAccessContext(), {"authorized_customer_id": 7}, 7])
def test_missing_or_user_declared_identity_denied_before_query(access: object) -> None:
    repository = Mock(spec=OrderRepository)
    with pytest.raises(OrderAccessDenied, match="^forbidden$"):
        OrderService(repository).get_status(3, access=access)
    repository.get_authorized_order.assert_not_called()


def test_authorized_historical_total_and_missing_tracking(order: OrderRecord) -> None:
    repository = Mock(spec=OrderRepository)
    repository.get_authorized_order.return_value = order
    result = OrderService(repository).get_status(
        3, access=OrderAccessContext(authorized_customer_id=7)
    )
    repository.get_authorized_order.assert_called_once_with(3, 7)
    assert result.total_brl == Decimal("3450.00")
    assert result.tracking_code is None
    assert result.estimated_delivery is None
    assert result.tracking_status == "not_provided"
    assert result.status == "delivered"
    assert result.items[0].quantity == 2
    output = result.model_dump()
    assert not {"customer_id", "name", "phone", "email", "notes", "delivered_at"} & output.keys()
    assert "unit_price_at_purchase" not in output["items"][0]


def test_existing_tracking_is_preserved(order: OrderRecord) -> None:
    repository = Mock(spec=OrderRepository)
    repository.get_authorized_order.return_value = replace(order, tracking_code="DEMO-123")
    result = OrderService(repository).get_status(
        3, access=OrderAccessContext(authorized_customer_id=7)
    )
    assert result.tracking_status == "available"
    assert result.tracking_code == "DEMO-123"


def test_other_customer_and_missing_order_have_same_failure(order: OrderRecord) -> None:
    repository = Mock(spec=OrderRepository)
    service = OrderService(repository)
    messages = []
    for record in (None, replace(order, customer_id=8)):
        repository.get_authorized_order.return_value = record
        with pytest.raises(OrderAccessDenied) as exc:
            service.get_status(3, access=OrderAccessContext(authorized_customer_id=7))
        messages.append(str(exc.value))
    assert messages == ["forbidden", "forbidden"]


def test_bad_backend_context_and_order_id() -> None:
    with pytest.raises(ValidationError):
        OrderAccessContext(authorized_customer_id=-1)
    context = OrderAccessContext(authorized_customer_id=7)
    with pytest.raises(ValidationError):
        context.authorized_customer_id = 8
    repository = Mock(spec=OrderRepository)
    with pytest.raises(ValidationError):
        OrderService(repository).get_status(-1, access=context)
    repository.get_authorized_order.assert_not_called()


def test_order_repository_failure_is_safe() -> None:
    repository = Mock(spec=OrderRepository)
    repository.get_authorized_order.side_effect = RepositoryError("private")
    with pytest.raises(ServiceUnavailable, match="^service_unavailable$"):
        OrderService(repository).get_status(3, access=OrderAccessContext(authorized_customer_id=7))
