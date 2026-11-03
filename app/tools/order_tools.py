"""A autorização vem exclusivamente de argumento separado injetado pelo backend."""

from app.services.errors import OrderAccessDenied, ServiceUnavailable
from app.services.models import OrderAccessContext, OrderStatus
from app.services.order_service import OrderService
from app.tools.common import run_tool
from app.tools.schemas import OrderStatusData, OrderStatusInput, ToolResponse


class OrderTools:
    def __init__(self, service: OrderService) -> None:
        self.service = service

    def get_order_status(
        self,
        arguments: object,
        *,
        access: OrderAccessContext | None = None,
    ) -> ToolResponse[OrderStatusData]:
        def operation(params: OrderStatusInput) -> OrderStatus:
            if not isinstance(access, OrderAccessContext) or access.authorized_customer_id is None:
                raise OrderAccessDenied()
            result = self.service.get_status(params.order_id, access=access)
            if result.order_id != params.order_id:
                raise ServiceUnavailable()
            return result

        return run_tool(arguments, OrderStatusInput, OrderStatusData, operation)
