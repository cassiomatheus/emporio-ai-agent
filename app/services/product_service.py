"""Busca e disponibilidade comercial calculadas sobre o catálogo do snapshot."""

import unicodedata

from pydantic import JsonValue

from app.database.repository import ProductRecord, ProductRepository, RepositoryError
from app.services.errors import AmbiguousProduct, ProductNotFound, ServiceUnavailable
from app.services.models import ID_ADAPTER, CatalogFacet, ProductDetails, ProductPage, ProductSearch
from app.services.money import from_cents


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def is_available(product: ProductRecord) -> bool:
    return product.status == "active" and product.stock_quantity > 0


def _details(product: ProductRecord) -> ProductDetails:
    reason = (
        product.status
        if product.status != "active"
        else ("available" if product.stock_quantity > 0 else "out_of_stock")
    )
    data = {key: value for key, value in vars(product).items() if key != "price_cents"}
    return ProductDetails(
        **data,
        price_brl=from_cents(product.price_cents),
        available=is_available(product),
        availability_reason=reason,
    )


def _matches_specs(actual: dict[str, JsonValue], expected: dict[str, JsonValue]) -> bool:
    indexed = {normalize_text(key): value for key, value in actual.items()}
    for key, value in expected.items():
        key = normalize_text(key)
        if key not in indexed:
            return False
        candidate = indexed[key]
        if isinstance(candidate, str) and isinstance(value, str):
            if normalize_text(candidate) != normalize_text(value):
                return False
        elif type(candidate) is not type(value) or candidate != value:
            return False
    return True


class ProductService:
    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    def catalog_facets(self) -> tuple[CatalogFacet, ...]:
        """Vocabulário observado, sem preços, estoque ou informações de clientes."""
        try:
            records = self.repository.list_products()
        except RepositoryError as exc:
            raise ServiceUnavailable() from exc
        return tuple(
            CatalogFacet(
                category_id=item.category_id,
                category_name=item.category_name,
                name=item.name,
                specs=item.specs,
            )
            for item in records
        )

    def get_product(self, product_id: int) -> ProductDetails:
        product_id = ID_ADAPTER.validate_python(product_id)
        try:
            product = self.repository.get_product(product_id)
        except RepositoryError as exc:
            raise ServiceUnavailable() from exc
        if product is None:
            raise ProductNotFound()
        return _details(product)

    def search(self, query: ProductSearch) -> ProductPage:
        try:
            records = self.repository.list_products()
        except RepositoryError as exc:
            raise ServiceUnavailable() from exc
        selected = []
        for product in records:
            if query.available_only and not is_available(product):
                continue
            if query.status is not None and product.status != query.status:
                continue
            if query.term and normalize_text(query.term) not in normalize_text(product.name):
                continue
            if any(
                normalize_text(term) not in normalize_text(product.name)
                for term in query.name_terms
            ):
                continue
            if query.category and normalize_text(query.category) != normalize_text(
                product.category_name
            ):
                continue
            if query.category_id is not None and product.category_id != query.category_id:
                continue
            price = from_cents(product.price_cents)
            if query.min_price is not None and price < query.min_price:
                continue
            if query.max_price is not None and price > query.max_price:
                continue
            if not _matches_specs(product.specs, query.specs):
                continue
            selected.append(product)
        selected.sort(key=lambda product: (product.price_cents, product.product_id))
        items = tuple(_details(row) for row in selected[query.offset : query.offset + query.limit])
        return ProductPage(items=items, total=len(selected), limit=query.limit, offset=query.offset)

    def get_product_by_name(self, name: str) -> ProductDetails:
        query = ProductSearch(term=name, available_only=False)
        try:
            records = self.repository.list_products()
        except RepositoryError as exc:
            raise ServiceUnavailable() from exc
        matches = [
            product
            for product in records
            if normalize_text(product.name) == normalize_text(query.term)
        ]
        if not matches:
            raise ProductNotFound()
        if len(matches) > 1:
            raise AmbiguousProduct()
        return _details(matches[0])
