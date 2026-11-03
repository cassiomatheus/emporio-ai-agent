"""UI local: assets restritos, texto seguro, sessões e projeção pública de tools."""

from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.database.ingestion import ingest_dataset


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.fixture
def client(tmp_path):
    database = tmp_path / "demo.sqlite3"
    ingest_dataset(Path("data/samples"), database)
    settings = Settings(_env_file=None, chat_mode="offline_demo", chat_demo_database=database)
    with TestClient(create_app(settings)) as client:
        yield client


def test_ui_and_assets_are_local_without_inline_execution(client):
    response = client.get("/")
    assert response.status_code == 200 and "text/html" in response.headers["content-type"]
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["referrer-policy"] == "no-referrer"
    page = Page()
    page.feed(response.text)
    assert next(attrs for tag, attrs in page.elements if tag == "html")["lang"] == "pt-BR"
    assert {attrs.get("id") for _, attrs in page.elements} >= {
        "chat-form",
        "message",
        "send",
        "new-chat",
        "messages",
        "mode-label",
        "tool-list",
    }
    for tag, attrs in page.elements:
        assert not any(key.startswith("on") for key in attrs)
        if tag == "script":
            assert attrs["src"] == "/assets/chat.js" and attrs["type"] == "module"
    for path in ("/assets/chat.css", "/assets/chat.js"):
        asset = client.get(path)
        assert asset.status_code == 200 and asset.text
        assert "nosniff" in asset.headers["x-content-type-options"]


@pytest.mark.parametrize(
    "path",
    [
        "/assets/.env",
        "/assets/raw/products.csv",
        "/assets/data/emporio.sqlite3",
        "/assets/AGENTS.md",
        "/web/index.html",
    ],
)
def test_static_routes_do_not_publish_the_project_or_private_sources(client, path):
    assert client.get(path).status_code == 404


def test_chat_ui_contract_exposes_only_public_trace_and_keeps_order_denial(client):
    identity = client.post("/sessions", json={}).json()
    headers = {"Authorization": "Bearer " + identity["session_token"]}

    def ask(text):
        return client.post(
            "/chat",
            headers=headers,
            json={
                "session_id": identity["session_id"],
                "message": text,
            },
        )

    response = ask("Mostre o produto 102")
    assert response.status_code == 200
    data = response.json()
    assert data["execution_mode"] == "offline_scripted"
    assert data["tools"] == [{"name": "get_product_details", "status": "ok", "error_code": None}]
    assert all(set(tool) == {"name", "status", "error_code"} for tool in data["tools"])
    assert identity["session_token"] not in response.text
    assert identity["session_id"] not in response.text
    assert "237,50" in ask("E no PIX?").json()["text"]
    denied = ask("Consulte pedido 1")
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "forbidden"
    assert "tools" not in denied.json() and "999,90" not in denied.text


def test_page_still_loads_when_runtime_is_unavailable(tmp_path):
    settings = Settings(_env_file=None, llm_provider=None, chat_demo_database=tmp_path / "missing")
    with TestClient(create_app(settings)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").json()["chat_ready"] is False
        assert client.post("/sessions", json={}).status_code == 503
