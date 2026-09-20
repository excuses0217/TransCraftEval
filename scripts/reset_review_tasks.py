#!/usr/bin/env python3
"""Reset review-task history while preserving local media and object libraries."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()

    state_path = args.state.resolve()
    backup_dir = args.backup_dir.resolve()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    previous_tasks = list(state.get("review_tasks", []))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"state-before-review-reset-{timestamp}.json"
    shutil.copy2(state_path, backup_path)

    state["review_tasks"] = []
    temporary_path = state_path.with_suffix(".reset.tmp")
    temporary_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(state_path)

    print(
        json.dumps(
            {
                "state": str(state_path),
                "backup": str(backup_path),
                "removed_review_tasks": len(previous_tasks),
                "preserved_library_items": len(state.get("library_items", [])),
                "preserved_media_items": len(state.get("media_items", [])),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
