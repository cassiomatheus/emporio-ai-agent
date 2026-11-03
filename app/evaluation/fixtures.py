"""Fixtures temporárias da avaliação; jamais altera CSV, PDF ou SQLite original."""

from pathlib import Path

import pymupdf

from app.database.connection import connect_database
from app.database.ingestion import ingest_dataset

PROJECT = Path(__file__).resolve().parents[2]


def prepare_databases(directory: Path) -> tuple[Path, Path]:
    catalog, orders = directory / "catalog.sqlite3", directory / "demo.sqlite3"
    for path in (catalog, orders):
        ingest_dataset(PROJECT / "data" / "samples", path)
    with connect_database(catalog) as connection:
        connection.execute("UPDATE categories SET name='Violões' WHERE category_id=1")
        connection.execute("INSERT INTO categories VALUES (3, 'Ukuleles', 'Categoria sintética')")
        connection.execute("UPDATE products SET category_id=3 WHERE product_id=127")
        connection.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                103,
                96000,
                "Violão sintético para parcelas",
                1,
                "Fixture da avaliação",
                3,
                "active",
                '{"strings":"nylon","color":"natural"}',
                "2026-01-01",
            ),
        )
    return catalog, orders


def prepare_policy_pdf(path: Path) -> None:
    """Conteúdo redistribuível, criado para testes; não é cópia do manual interno."""
    sections = [
        ("3", "Pagamento PIX", "PIX: desconto de 5% sobre preco de tabela, a vista."),
        (
            "3.1",
            "Parcelamento",
            "Ate 12x sem juros. De 4x a 6x: parcela minima R$ 80. "
            "De 7x a 12x: parcela minima R$ 100. Em 2x e 3x, adotar piso conservador R$ 50.",
        ),
        (
            "4.1",
            "Devolucao por arrependimento",
            "Compra online: ate 7 dias corridos do "
            "recebimento real. Embalagem original, sem uso, com componentes. "
            "Loja paga retorno. Reembolso na mesma modalidade em ate 10 dias uteis.",
        ),
        (
            "4.2",
            "Troca por defeito",
            "Troca por defeito de fabricacao em ate 30 dias da compra. "
            "Procedimento distinto da garantia legal de 90 dias do recebimento.",
        ),
        (
            "5.1",
            "Frete metropolitano",
            "Regiao metropolitana: gratis acima de R$ 500. "
            "Abaixo de R$ 500: R$ 35. Valor exatamente R$ 500 nao definido; confirmar com a loja.",
        ),
        (
            "6.2",
            "Promocoes",
            "Promocoes nao acumulam com desconto PIX. Consultar condicoes registradas no snapshot.",
        ),
        (
            "8.1",
            "Garantia legal",
            "Garantia legal de 90 dias a partir do recebimento, "
            "para defeito de fabricacao. Nao confundir com troca em 30 dias da compra.",
        ),
    ]
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 70), "Politicas sinteticas de avaliacao. Versao 0.1")
        page.insert_text((72, 110), "2. Horarios", fontname="hebo", fontsize=14)
        page.draw_rect(pymupdf.Rect(72, 145, 500, 215))
        page.draw_line((250, 145), (250, 215))
        page.draw_line((72, 180), (500, 180))
        for x, y, text in [
            (80, 168, "Dia"),
            (260, 168, "Horario"),
            (80, 203, "Sabado"),
            (260, 203, "09h-13h"),
        ]:
            page.insert_text((x, y), text)
        for section, title, text in sections:
            page = document.new_page()
            page.insert_text((72, 80), f"{section} {title}", fontname="hebo", fontsize=14)
            page.insert_textbox(pymupdf.Rect(72, 115, 520, 600), text, fontsize=11)
        document.save(path)
