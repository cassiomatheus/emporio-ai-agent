"""Interface local estática; somente estes assets são publicados pelo servidor."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

WEB = Path(__file__).resolve().parent / "web"
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'self'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def mount_chat_ui(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    async def chat_page():
        return FileResponse(WEB / "index.html", media_type="text/html", headers=HEADERS)

    @app.get("/assets/chat.css", include_in_schema=False)
    async def chat_styles():
        return FileResponse(WEB / "chat.css", media_type="text/css", headers=HEADERS)

    @app.get("/assets/chat.js", include_in_schema=False)
    async def chat_script():
        return FileResponse(WEB / "chat.js", media_type="text/javascript", headers=HEADERS)
