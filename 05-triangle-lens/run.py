"""Start TriageLens:  python run.py   (then open http://localhost:8000)"""
import os
import threading
import webbrowser

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    if host in ("127.0.0.1", "localhost") and not os.environ.get("NO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run("server:app", host=host, port=port)
