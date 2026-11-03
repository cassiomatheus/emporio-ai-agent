"""Contratos de tools com serviços reais e repositórios simulados, sem SQLite/LLM."""

import json
import warnings
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.database.repository import (
    OrderItemRecord,
    OrderRecord,
    OrderRepository,
    PricingRepository,
    ProductRecord,
    ProductRepository,
    PromotionRecord,
)
from app.retrieval.models import (
    ChunkMetadata,
    DocumentPage,
    DocumentTable,
    PolicyChunk,
    PolicyDocument,
    PolicySection,
)
from app.retrieval.retriever import LexicalRetriever
from app.services.models import OrderAccessContext, ProductSearch
from app.services.order_service import OrderService
from app.services.policy_service import PolicyService, StoreInfo
from app.services.pricing_service import PricingService
from app.services.product_service import ProductService
from app.tools.registry import ToolRegistry, tool_contracts
from app.tools.schemas import RESPONSE_MODELS


def synthetic_policies() -> PolicyService:
    chunks = []
    for number, (section, title, headers, rows, text) in enumerate(
        [
            (
                "1.2",
                "Dados da Empresa",
                ("Campo", "Informação"),
                (
                    ("Endereço", "Rua Sintética, 1"),
                    ("Telefone / WhatsApp", "(00) 1111-1111"),
                    ("E-mail", "a@loja.example.invalid"),
                    ("CNPJ", "PRIVATE-TAX-MARKER"),
                ),
                "",
            ),
            (
                "2",
                "Horário de Funcionamento",
                ("Dia", "Horário"),
                (
                    ("Segunda a Sexta", "09:00 às 18:00"),
                    ("Sábado", "09:00 às 13:00"),
                    ("Domingo", "Fechado"),
                ),
                "",
            ),
            ("3", "Pagamento", ("Forma", "Condição"), (("PIX", "Desconto sintético"),), ""),
            ("7", "Atendimento", (), (), "WhatsApp (00) 2222-2222, contato público sintético."),
        ]
    ):
        table = DocumentTable(page=2, headers=headers, rows=rows) if headers else None
        if table:
            text = "\n".join(
                " | ".join(f"{h}: {c}" for h, c in zip(headers, row, strict=True)) for row in rows
            )
        chunks.append(
            PolicyChunk(
                chunk_id=f"synthetic:{number}",
                kind="table" if table else "paragraph",
                text=text,
                table=table,
                metadata=ChunkMetadata(
                    source_name="synthetic.pdf",
                    source_sha256="0" * 64,
                    version="0.1",
                    section_id=section,
                    section_title=title,
                    section_path=(title,),
                    pages=(2,),
                    section_pages=(2,),
                ),
            )
        )
    document = PolicyDocument(
        source_name="synthetic.pdf",
        source_sha256="0" * 64,
        version="0.1",
        pages=(
            DocumentPage(
                number=1,
                printed_label=None,
                text="PRIVATE-COVER-MARKER (00) 1111-1111 b@loja.example.invalid",
            ),
        ),
        sections=tuple(
            PolicySection(
                section_id=c.metadata.section_id, title=c.metadata.section_title, pages=(2,)
            )
            for c in chunks
        ),
        chunks=tuple(chunks),
    )
    return PolicyService(LexicalRetriever(document))


@pytest.fixture
def services(product: ProductRecord) -> dict:
    catalog = (
        product,
        replace(product, product_id=127, name="Instrumento Sintético em Oferta", price_cents=35900),
    )
    products = Mock(spec=ProductRepository)
    products.list_products.return_value = catalog
    products.get_product.side_effect = lambda pid: next(
        (p for p in catalog if p.product_id == pid), None
    )
    pricing = Mock(spec=PricingRepository)
    pricing.get_pricing_data.side_effect = lambda pid: (
        (catalog[1], (PromotionRecord(12, 127, 10, 1),)) if pid == 127 else None
    )
    order = OrderRecord(
        order_id=1,
        customer_id=7,
        order_date="2026-01-01",
        status="delivered",
        total_cents=345000,
        payment_method="pix",
        tracking_code=None,
        estimated_delivery=None,
        items=(OrderItemRecord(127, "Instrumento Sintético", 1),),
    )
    orders = Mock(spec=OrderRepository)
    orders.get_authorized_order.side_effect = lambda oid, cid: (
        order if oid == 1 and cid == 7 else None
    )
    return {
        "products": ProductService(products),
        "pricing": PricingService(pricing),
        "orders": OrderService(orders),
        "policies": synthetic_policies(),
    }


@pytest.fixture
def tools(services: dict) -> ToolRegistry:
    return ToolRegistry(**services)


SUCCESS_CASES = [
    (
        "search_products",
        {"category": "Violões", "max_price": "800.00", "specs": {"strings": "nylon"}},
    ),
    ("get_product_details", {"product_id": 127}),
    ("get_product_offers", {"product_id": 127, "payment_method": "pix"}),
    ("get_order_status", {"order_id": 1}),
    ("search_store_policies", {"query": "PIX"}),
    ("get_store_info", {"subject": "address"}),
]


@pytest.mark.parametrize("name,arguments", SUCCESS_CASES)
def test_six_success_contracts_round_trip(tools: ToolRegistry, name: str, arguments: dict) -> None:
    response = tools.call(
        name, arguments, order_access=OrderAccessContext(authorized_customer_id=7)
    )
    assert response.status == "ok", response.error
    assert response.error is None
    parsed = RESPONSE_MODELS[name].model_validate_json(response.model_dump_json())
    assert parsed.status == "ok"
    assert json.loads(response.model_dump_json())["data"] is not None


def test_schema_inventory_and_authorization_never_in_arguments() -> None:
    contracts = tool_contracts()
    assert {item["name"] for item in contracts} == {name for name, _ in SUCCESS_CASES}
    assert len(contracts) == 6
    json.dumps(contracts, allow_nan=False)
    for contract in contracts:
        schema = contract["input_schema"]
        assert schema["additionalProperties"] is False
        assert (
            not {"sql", "database", "path", "customer_id", "access", "order_access"}
            & schema["properties"].keys()
        )
    orders = next(item for item in contracts if item["name"] == "get_order_status")
    assert set(orders["input_schema"]["properties"]) == {"order_id"}
    assert "OrderAccessContext" not in json.dumps(orders)


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("search_products", {"limit": 0}),
        ("search_products", {"limit": 21}),
        ("search_products", {"offset": -1}),
        ("search_products", {"term": "x" * 121}),
        ("search_products", {"min_price": "800", "max_price": "400"}),
        ("search_products", {"max_price": 800.0}),
        ("search_products", {"max_price": "NaN"}),
        ("search_products", {"max_price": "0.001"}),
        ("search_products", {"available_only": "true"}),
        ("search_products", {"specs": {"key": {"nested": "x"}}}),
        ("search_products", {"specs": {"k": "x" * 121}}),
        ("get_product_details", {}),
        ("get_product_details", {"product_id": True}),
        ("get_product_details", {"product_id": "127"}),
        ("get_product_details", {"product_id": 127, "name": "x"}),
        ("get_product_offers", {"product_id": 127, "installments": 3}),
        ("get_product_offers", {"product_id": 127, "payment_method": "credit", "installments": 13}),
        ("get_product_offers", {"product_id": 127, "payment_method": "pix", "installments": 2}),
        ("get_order_status", {"order_id": 0}),
        ("get_order_status", {"order_id": 1, "customer_id": 7}),
        ("get_order_status", {"order_id": 1, "access": {"authorized_customer_id": 7}}),
        ("search_store_policies", {"query": " "}),
        ("search_store_policies", {"query": "x" * 501}),
        ("search_store_policies", {"query": "pix", "top_k": 6}),
        ("get_store_info", {"subject": "open_now"}),
    ],
)
def test_invalid_inputs_are_structured(tools: ToolRegistry, name: str, arguments: dict) -> None:
    result = tools.call(name, arguments)
    assert result.status == "error"
    assert result.data is None
    assert result.error.code == "invalid_arguments"
    assert RESPONSE_MODELS[name].model_validate_json(result.model_dump_json()).status == "error"


@pytest.mark.parametrize(
    "arguments", [None, [], "{}", {"term": "x" * 9000}, {"specs": {"x": float("nan")}}]
)
def test_json_object_and_size_limits(tools: ToolRegistry, arguments: object) -> None:
    assert tools.call("search_products", arguments).error.code == "invalid_arguments"


def test_decimal_strings_and_integer_prices_with_promotion(tools: ToolRegistry) -> None:
    assert tools.call("search_products", {"max_price": 800}).status == "ok"
    result = tools.call("get_product_offers", {"product_id": 127, "payment_method": "pix"})
    assert result.data.original_price == Decimal("359.00")
    assert result.data.options[0].final_price == Decimal("323.10")
    assert result.data.options[0].discount_percent == 10
    assert "RN-04" in result.data.applied_rules
    serialized = json.loads(result.model_dump_json())
    assert serialized["data"]["options"][0]["final_price"] == "323.10"
    assert (
        tools.call("get_product_offers", {"product_id": 127}).data.options[1].eligible_installments
    )
    assert (
        tools.call(
            "get_product_offers", {"product_id": 127, "payment_method": "credit", "installments": 6}
        ).error.code
        == "invalid_installments"
    )


def test_exact_product_name_and_missing_product(tools: ToolRegistry) -> None:
    assert (
        tools.call("get_product_details", {"name": " VIOLAO SINTETICO NYLON "}).data.product_id
        == 81
    )
    assert tools.call("get_product_details", {"name": "Violão"}).error.code == "not_found"
    assert tools.call("get_product_details", {"product_id": 999}).error.code == "not_found"
    assert tools.call("get_product_offers", {"product_id": 999}).error.code == "not_found"


def test_ambiguous_name_does_not_pick_a_product(
    tools: ToolRegistry, services: dict, product: ProductRecord
) -> None:
    services["products"].repository.list_products.return_value = (
        product,
        replace(product, product_id=82),
    )
    assert tools.call("get_product_details", {"name": product.name}).error.code == "ambiguous"


def test_empty_catalog_and_policy_absence(tools: ToolRegistry) -> None:
    result = tools.call("search_products", {"term": "unknown"})
    assert result.status == "ok" and result.data.items == () and result.data.total == 0
    assert (
        tools.call("search_store_policies", {"query": "viagem intergalactica"}).error.code
        == "no_evidence"
    )


@pytest.mark.parametrize("context", [None, OrderAccessContext(), {"authorized_customer_id": 7}, 7])
def test_no_backend_authorization_never_reads_orders(
    tools: ToolRegistry, services: dict, context: object
) -> None:
    result = tools.call("get_order_status", {"order_id": 1}, order_access=context)
    assert result.error.code == "forbidden"
    services["orders"].repository.get_authorized_order.assert_not_called()


def test_authorized_status_and_indistinguishable_denial(tools: ToolRegistry) -> None:
    own = tools.call(
        "get_order_status",
        {"order_id": 1},
        order_access=OrderAccessContext(authorized_customer_id=7),
    )
    assert own.data.total_brl == Decimal("3450.00")
    assert own.data.tracking_code is None and own.data.tracking_status == "not_provided"
    assert not {"customer_id", "notes", "email", "phone"} & own.data.model_dump().keys()
    other = tools.call(
        "get_order_status",
        {"order_id": 1},
        order_access=OrderAccessContext(authorized_customer_id=8),
    )
    missing = tools.call(
        "get_order_status",
        {"order_id": 999},
        order_access=OrderAccessContext(authorized_customer_id=8),
    )
    assert other.model_dump() == missing.model_dump()


def test_store_public_info_with_citations_and_conflict_warnings(tools: ToolRegistry) -> None:
    address = tools.call("get_store_info", {"subject": "address"})
    assert address.data.entries[0].value == "Rua Sintética, 1"
    assert address.data.entries[0].source.section_id == "1.2"
    contacts = tools.call("get_store_info", {"subject": "contacts"})
    assert {
        "conflicting_phone_numbers",
        "conflicting_emails",
        "confirm_contacts_with_store",
    } <= set(contacts.data.cautions)
    assert {entry.source.section_id for entry in contacts.data.entries} == {None, "1.2", "7"}
    assert "PRIVATE" not in contacts.model_dump_json()
    hours = tools.call("get_store_info", {"subject": "hours"})
    assert len(hours.data.entries) == 3
    assert "not_an_open_now_check" in hours.data.cautions


@pytest.mark.parametrize("name,arguments", SUCCESS_CASES)
def test_service_exceptions_never_leak_data(
    tools: ToolRegistry, services: dict, monkeypatch, name: str, arguments: dict
) -> None:
    target, method = {
        "search_products": ("products", "search"),
        "get_product_details": ("products", "get_product"),
        "get_product_offers": ("pricing", "quote"),
        "get_order_status": ("orders", "get_status"),
        "search_store_policies": ("policies", "search"),
        "get_store_info": ("policies", "get_store_info"),
    }[name]

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-SECRET customer@example.invalid SELECT * FROM customers")

    monkeypatch.setattr(services[target], method, fail)
    response = tools.call(
        name, arguments, order_access=OrderAccessContext(authorized_customer_id=7)
    )
    assert response.error.code == "service_unavailable" and response.data is None
    assert "PRIVATE" not in response.model_dump_json()
    assert "example.invalid" not in response.model_dump_json()


def test_malformed_and_oversized_outputs_fail_closed(
    tools: ToolRegistry, services: dict, monkeypatch
) -> None:
    monkeypatch.setattr(
        services["orders"], "get_status", lambda *args, **kwargs: {"email": "PRIVATE-SECRET"}
    )
    assert (
        tools.call(
            "get_order_status",
            {"order_id": 1},
            order_access=OrderAccessContext(authorized_customer_id=7),
        ).error.code
        == "service_unavailable"
    )
    original = services["products"].get_product(81)
    monkeypatch.setattr(
        services["products"],
        "get_product",
        lambda pid: original.model_copy(update={"stock_quantity": "13"}),
    )
    with warnings.catch_warnings(record=True) as recorded:
        result = tools.call("get_product_details", {"product_id": 81})
    assert result.error.code == "service_unavailable"
    assert not recorded
    monkeypatch.setattr(
        services["products"],
        "get_product",
        lambda pid: original.model_copy(update={"description": "x" * 70000}),
    )
    assert tools.call("get_product_details", {"product_id": 81}).error.code == "response_too_large"


def test_unknown_tools_sql_and_private_argument_keys_are_not_executed(tools: ToolRegistry) -> None:
    assert tools.call("execute_sql", {"sql": "DROP TABLE products"}).error.code == "unknown_tool"
    assert tools.call("__dict__", {}).error.code == "unknown_tool"
    assert (
        tools.call("search_products", {"sql": "SELECT * FROM customers"}).error.code
        == "invalid_arguments"
    )
    assert tools.call("search_products", {"term": "' OR 1=1 --"}).data.items == ()
    response = tools.call("get_product_details", {"private@example.invalid": "secret"})
    assert "private@example.invalid" not in response.model_dump_json()


def test_missing_policy_service_does_not_invent_evidence(services: dict) -> None:
    registry = ToolRegistry(**{**services, "policies": None})
    assert (
        registry.call("get_store_info", {"subject": "address"}).error.code == "service_unavailable"
    )
    assert (
        registry.call("search_store_policies", {"query": "PIX"}).error.code == "service_unavailable"
    )
    assert registry.call("get_product_details", {"product_id": 127}).status == "ok"


def test_empty_store_info_and_authorization_before_service(
    tools: ToolRegistry,
    services: dict,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        services["policies"],
        "get_store_info",
        lambda subject: StoreInfo(
            subject=subject,
            entries=(),
            cautions=(),
        ),
    )
    assert tools.call("get_store_info", {"subject": "address"}).error.code == "no_evidence"
    probe = Mock(side_effect=RuntimeError("should not be invoked"))
    monkeypatch.setattr(services["orders"], "get_status", probe)
    assert tools.call("get_order_status", {"order_id": 1}).error.code == "forbidden"
    probe.assert_not_called()


def test_result_identity_and_pagination_are_bound_to_request(
    tools: ToolRegistry,
    services: dict,
    monkeypatch,
) -> None:
    page = services["products"].search(ProductSearch(limit=20))
    monkeypatch.setattr(services["products"], "search", lambda query: page)
    assert tools.call("search_products", {"limit": 1}).error.code == "service_unavailable"
    product = services["products"].get_product(81)
    monkeypatch.setattr(services["products"], "get_product", lambda product_id: product)
    assert (
        tools.call("get_product_details", {"product_id": 127}).error.code == "service_unavailable"
    )
