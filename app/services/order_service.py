"""Consulta protegida, com autorização injetada pelo backend e saída mínima."""

from app.database.repository import OrderRepository, RepositoryError
from app.services.errors import OrderAccessDenied, ServiceUnavailable
from app.services.models import ID_ADAPTER, OrderAccessContext, OrderItem, OrderStatus
from app.services.money import from_cents


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    def get_status(self, order_id: int, *, access: OrderAccessContext | None = None) -> OrderStatus:
        if not isinstance(access, OrderAccessContext) or access.authorized_customer_id is None:
            raise OrderAccessDenied()
        order_id = ID_ADAPTER.validate_python(order_id)
        try:
            order = self.repository.get_authorized_order(order_id, access.authorized_customer_id)
        except RepositoryError as exc:
            raise ServiceUnavailable() from exc
        # Pedido alheio e ID inexistente são indistinguíveis para o solicitante.
        if order is None or order.customer_id != access.authorized_customer_id:
            raise OrderAccessDenied()
        return OrderStatus(
            order_id=order.order_id,
            order_date=order.order_date,
            status=order.status,
            total_brl=from_cents(order.total_cents),
            payment_method=order.payment_method,
            tracking_code=order.tracking_code,
            estimated_delivery=order.estimated_delivery,
            tracking_status="available" if order.tracking_code is not None else "not_provided",
            items=tuple(OrderItem(**vars(item)) for item in order.items),
        )
