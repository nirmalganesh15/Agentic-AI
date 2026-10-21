import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    reload = os.getenv("RELOAD", "true").lower() == "true"
    uvicorn.run(
        "rag.api:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=reload,
        reload_dirs=["src"] if reload else None,
    )


if __name__ == "__main__":
    main()
