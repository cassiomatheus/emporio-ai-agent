"""CLI local, sem UI web: mesmo runtime, backend e orquestrador da API."""

import argparse
import asyncio
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from app.agent.models import AgentRequest
from app.config import Settings
from app.interface_errors import MESSAGES, result_error
from app.runtime import RuntimeUnavailable, build_runtime


async def run_cli(settings: Settings, *, message: str | None, demo_order: bool) -> int:
    if demo_order and settings.chat_mode != "offline_demo":
        print(
            "--demo-order exige --offline-demo e usa somente o cliente sintético 1.",
            file=sys.stderr,
        )
        return 2
    runtime = await build_runtime(settings)
    client = None
    try:
        client = runtime.backend.register_demo_client(customer_id=1 if demo_order else None)
        session = runtime.backend.create_session(client)
        print(f"Modo: {runtime.execution_mode}. Sem autenticação real.")
        while True:
            if message is None:
                try:
                    text = input("Você (/sair para encerrar): ")
                except EOFError:
                    return 0
                if text.strip() == "/sair":
                    return 0
            else:
                text = message
            try:
                request = AgentRequest(message=text)
                if not text.strip():
                    raise ValueError("blank_message")
            except (ValidationError, ValueError):
                print(MESSAGES["invalid_request"], file=sys.stderr)
                if message is not None:
                    return 2
                continue
            result = await runtime.backend.chat(client, session, request)
            error = result_error(result)
            if error:
                print(MESSAGES[error[1]], file=sys.stderr)
                if message is not None:
                    return 1
            else:
                print(result.text)
                if message is not None:
                    return 0 if result.status == "answered" else 1
    finally:
        if client is not None:
            runtime.backend.revoke_client(client)
        await runtime.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atendimento local da Empório da Música.")
    parser.add_argument(
        "--offline-demo", action="store_true", help="Roteiro simulado, sem LLM/rede."
    )
    parser.add_argument(
        "--demo-order", action="store_true", help="Autoriza apenas cliente sintético 1."
    )
    parser.add_argument("--message", help="Uma mensagem; sem esta opção, conversa interativa.")
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        if args.offline_demo:
            settings = settings.model_copy(update={"chat_mode": "offline_demo"})
        return asyncio.run(run_cli(settings, message=args.message, demo_order=args.demo_order))
    except KeyboardInterrupt:
        return 0
    except RuntimeUnavailable:
        print(MESSAGES["service_unavailable"], file=sys.stderr)
        return 2
    except Exception:
        print(MESSAGES["internal_error"], file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
