from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn


SERVICE_DIR = Path(__file__).resolve().parent
ENV_FILE = SERVICE_DIR / ".env"
load_dotenv(ENV_FILE)


def get_host() -> str:
    return os.getenv("ASK_HOST", "127.0.0.1")


def get_port() -> int:
    return int(os.getenv("ASK_PORT", "18082"))


def main() -> None:
    uvicorn.run(
        "app:app",
        host=get_host(),
        port=get_port(),
        workers=1,
    )


if __name__ == "__main__":
    main()
