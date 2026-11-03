"""Pedidos de demonstração vêm exclusivamente das fixtures sintéticas locais."""

import json
from decimal import Decimal
from pathlib import Path

from app.database.connection import connect_database
from app.database.dataset import load_dataset
from app.database.models import ROW_MODELS, SourceRow

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


def _canonical(row: SourceRow) -> str:
    data = row.model_dump(mode="json")
    for name in ("price_brl", "total_brl"):
        if name in data:
            data[name] = format(Decimal(data[name]), ".2f")
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


class DemoDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        dataset = load_dataset(SAMPLES)
        if not dataset.report.valid:
            raise ValueError("demo_fixtures_unavailable")
        self._expected = {
            table: sorted(_canonical(row) for row in rows) for table, rows in dataset.tables.items()
        }
        self.customer_ids = frozenset(row.customer_id for row in dataset.tables["customers"])
        if not self.valid():
            raise ValueError("synthetic_demo_database_required")

    def valid(self) -> bool:
        """Só leituras; nenhuma migração ou cópia de PII do snapshot original."""
        try:
            with connect_database(self.path, read_only=True) as connection:
                connection.execute("BEGIN")
                for table, model in ROW_MODELS.items():
                    rows = []
                    # table vem de constantes do código, nunca de mensagem ou tool.
                    for record in connection.execute(f"SELECT * FROM {table}"):
                        data = dict(record)
                        for money in ("price", "total"):
                            if f"{money}_cents" in data:
                                data[f"{money}_brl"] = Decimal(data.pop(f"{money}_cents")) / 100
                        rows.append(_canonical(model.model_validate(data)))
                    if sorted(rows) != self._expected[table]:
                        return False
                return not connection.execute("PRAGMA foreign_key_check").fetchall()
        except Exception:
            return False
