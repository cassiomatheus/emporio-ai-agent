"""Tools de catálogo delegam filtros e disponibilidade ao ProductService."""

from app.services.errors import ServiceUnavailable
from app.services.models import ProductDetails, ProductPage, ProductSearch
from app.services.product_service import ProductService
from app.tools.common import run_tool
from app.tools.schemas import (
    ProductDetailsInput,
    SearchProductsData,
    SearchProductsInput,
    ToolResponse,
)


class ProductTools:
    def __init__(self, service: ProductService) -> None:
        self.service = service

    def search_products(self, arguments: object) -> ToolResponse[SearchProductsData]:
        def operation(params: SearchProductsInput) -> ProductPage:
            result = self.service.search(ProductSearch(**params.model_dump()))
            if (
                result.limit != params.limit
                or result.offset != params.offset
                or len(result.items) > params.limit
            ):
                raise ServiceUnavailable()
            return result

        return run_tool(
            arguments,
            SearchProductsInput,
            SearchProductsData,
            operation,
        )

    def get_product_details(self, arguments: object) -> ToolResponse[ProductDetails]:
        def operation(params: ProductDetailsInput) -> ProductDetails:
            if params.product_id is not None:
                result = self.service.get_product(params.product_id)
                if result.product_id != params.product_id:
                    raise ServiceUnavailable()
                return result
            return self.service.get_product_by_name(params.name)

        return run_tool(arguments, ProductDetailsInput, ProductDetails, operation)
