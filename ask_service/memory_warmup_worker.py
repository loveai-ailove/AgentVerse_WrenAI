from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from wren.memory.store import MemoryStore


def main() -> int:
    if len(sys.argv) != 3:
        print(
            json.dumps(
                {"ok": False, "error": "用法错误，需要传入 memory_path 和 model_name"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    memory_path = Path(sys.argv[1]).expanduser().resolve()
    model_name = sys.argv[2]
    started = time.perf_counter()
    try:
        MemoryStore(path=memory_path, model_name=model_name)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "memory_path": str(memory_path),
                    "model_name": model_name,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "memory_path": str(memory_path),
                "model_name": model_name,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
