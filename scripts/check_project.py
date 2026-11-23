"""Dependency-free structural checks for the TaskFlow repository."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "app.py",
    "requirements.txt",
    "render.yaml",
    ".env.example",
    ".gitignore",
    "static/index.html",
    "static/app.js",
    "static/style.css",
)


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def main() -> int:
    missing = [item for item in REQUIRED_FILES if not (ROOT / item).is_file()]
    if missing:
        fail("missing required project files: " + ", ".join(missing))

    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    css = (ROOT / "static/style.css").read_text(encoding="utf-8")
    js = (ROOT / "static/app.js").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    for asset in ("/static/style.css", "/static/app.js"):
        if asset not in html:
            fail(f"static/index.html does not reference {asset}")

    for element_id in ("taskList", "taskForm", "taskTitle", "openForm", "toast"):
        if f'id="{element_id}"' not in html:
            fail(f"static/index.html is missing element id={element_id}")

    for route in (
        '@app.get("/health")',
        '@app.get("/api/tasks")',
        '@app.post("/api/tasks")',
        '@app.patch("/api/tasks/{task_id}")',
        '@app.delete("/api/tasks/{task_id}")',
    ):
        if route not in app:
            fail(f"app.py is missing expected route: {route}")

    for marker in ("validate_init_data", "current_user", "user_id"):
        if marker not in app:
            fail(f"app.py is missing security/data-isolation marker: {marker}")

    if ".env" not in gitignore:
        fail(".gitignore must exclude .env")

    token_pattern = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{25,}\b")
    for relative in ("app.py", "bot.py", ".env.example", "render.yaml"):
        path = ROOT / relative
        if path.exists() and token_pattern.search(path.read_text(encoding="utf-8")):
            fail(f"possible Telegram bot token found in {relative}")

    if not css.strip() or not js.strip():
        fail("static CSS/JavaScript assets must not be empty")

    print(
        "OK: required files, frontend references, API routes, auth markers, "
        ".env ignore rule, and token scan"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
