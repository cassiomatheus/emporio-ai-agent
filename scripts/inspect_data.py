"""Diagnóstico sanitizado: python scripts/inspect_data.py --raw-dir data/raw."""

import argparse
import sys
from pathlib import Path

from app.database.dataset import load_dataset
from app.database.ingestion import IngestionError, protect_output


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona os seis CSVs sem alterá-los.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--report", type=Path, help="Grava o mesmo relatório JSON exibido no stdout."
    )
    args = parser.parse_args()
    try:
        if args.report:
            protect_output(args.report, args.raw_dir, {".json"})
        report = load_dataset(args.raw_dir).report
        output = report.model_dump_json(indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(output + "\n", encoding="utf-8")
        print(output)
        return 0 if report.valid else 1
    except (OSError, IngestionError):
        print('{"error": "inspection_output_failed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
