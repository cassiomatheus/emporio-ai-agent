"""Ingestão local: python scripts/ingest_data.py --database data/emporio.sqlite3."""

import argparse
import json
import sys
from pathlib import Path

from app.database.dataset import DataQualityError
from app.database.ingestion import IngestionError, ingest_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Substitui o snapshot SQLite em uma transação.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--database", type=Path, default=Path("data/emporio.sqlite3"))
    args = parser.parse_args()
    try:
        result = ingest_dataset(args.raw_dir, args.database)
    except DataQualityError as exc:
        print(exc.report.model_dump_json(indent=2), file=sys.stderr)
        return 1
    except IngestionError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
