"""Ponto de entrada mínimo para verificar instalação e configuração."""

from app.config import Settings


def main() -> None:
    """Inicializa a configuração e informa o estágio atual do projeto."""
    settings = Settings()
    print(f"Empório da Música | ambiente: {settings.environment} | fase: 01")


if __name__ == "__main__":
    main()
