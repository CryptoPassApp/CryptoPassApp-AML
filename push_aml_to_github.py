"""Загрузка CryptoPassApp (AML-сканер) в GitHub через REST API (git не нужен).

Использование:
    python push_aml_to_github.py --dry-run   # показать, что будет загружено
    python push_aml_to_github.py             # загрузить

Токен: переменная GITHUB_TOKEN, либо github_token.txt рядом со скриптом,
либо github_token.txt в воркспейсе GiftTracker. Репозиторий:
CryptoPassApp/CryptoPassApp-AML (создаётся автоматически, если токен
имеет право создавать репозитории).

Секреты не уходят: .env, data/, __pycache__, *.pyc исключены.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import httpx

API = "https://api.github.com"
PROJECT = Path(__file__).resolve().parent
REPO = "CryptoPassApp/CryptoPassApp-AML"
BRANCH = "main"
# Токен GiftTracker лежит в соседнем воркспейсе — резервный источник.
GIFTTRACKER_TOKEN = Path(
    r"C:\Users\Нико\.zcode\workspace\f7dd6fd0-2717-4a02-88bb-95556b60b317\github_token.txt"
)

EXCLUDE_DIRS = {
    "__pycache__", "data", ".venv", "venv", ".git", ".idea", ".vscode",
    ".pytest_cache", "logs",
}
EXCLUDE_NAMES = {".env", ".env.local", "github_token.txt"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".db", ".db-shm", ".db-wal", ".exe", ".log", ".tar.gz"}
MAX_FILE_BYTES = 8 * 1024 * 1024
COMMIT_MESSAGE = (
    "CryptoPassApp: flash-token detector — jetton verification vs real USDT master, "
    "obfuscation-proof symbol normalization (zero-width/RTL/homoglyphs/tag chars), "
    "BLACKLIST + fake-stablecoin + dust-airdrop flags merged into risk score; "
    "TonAPIClient.get_jettons; deploy: systemd api+bot + Caddy on Oracle VPS; 13 tests"
)


def load_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        for candidate in (PROJECT / "github_token.txt", GIFTTRACKER_TOKEN):
            if candidate.exists():
                token = candidate.read_text(encoding="utf-8").strip()
                if token:
                    break
    if token.startswith("PASTE_") or " " in token or "\n" in token:
        return ""
    return token


def collect_files() -> list[tuple[str, Path]]:
    """Все файлы проекта, кроме секретов и мусора."""
    files: list[tuple[str, Path]] = []
    for path in sorted(PROJECT.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(PROJECT).parts
        if set(rel_parts) & EXCLUDE_DIRS:
            continue
        if path.name in EXCLUDE_NAMES or path.suffix in EXCLUDE_SUFFIXES:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        files.append((path.relative_to(PROJECT).as_posix(), path))
    return files


def api_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API,
        timeout=60,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CryptoPassApp-Uploader",
        },
    )


def fail(resp: httpx.Response, action: str) -> None:
    print(f"ОШИБКА {action}: HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False)[:1200])
    except Exception:  # noqa: BLE001
        print(resp.text[:800])
    sys.exit(1)


def ensure_repo(client: httpx.Client, token: str) -> None:
    info = client.get(f"/repos/{REPO}")
    if info.status_code == 200:
        print("Репозиторий существует:", REPO)
        return
    print("Репозитория нет — пробую создать…")
    created = client.post(
        "/user/repos",
        json={
            "name": REPO.split("/", 1)[1],
            "description": (
                "CryptoPassApp — AML wallet scanner / Trust Passport for TON+TRON: "
                "flash-token detector, risk scoring, Telegram Mini App + bot"
            ),
            "private": False,
            "auto_init": False,
        },
    )
    if created.status_code == 201:
        print("Создан:", created.json().get("html_url"))
    else:
        print(
            "НЕ удалось создать репозиторий (HTTP "
            f"{created.status_code}). Создай вручную: github.com/new → "
            "имя CryptoPassApp-AML, public, БЕЗ README — и запусти скрипт снова."
        )
        if created.status_code != 403:
            print(created.text[:400])
        sys.exit(1)


def push(token: str) -> None:
    files = collect_files()
    total = sum(p.stat().st_size for _, p in files)
    print(f"Файлов: {len(files)}, объём: {total / 1024:.1f} KB")

    with api_client(token) as client:
        me = client.get("/user")
        if me.status_code != 200:
            fail(me, "GET /user (проверь токен)")
        print("Пользователь:", me.json()["login"])

        ensure_repo(client, token)

        ref = client.get(f"/repos/{REPO}/git/ref/heads/{BRANCH}")
        parents: list[str] = []
        if ref.status_code == 200:
            parents = [ref.json()["object"]["sha"]]
            print("Текущий HEAD:", parents[0][:10])

        tree_entries = []
        for i, (rel, path) in enumerate(files, 1):
            content = base64.b64encode(path.read_bytes()).decode()
            resp = client.post(
                f"/repos/{REPO}/git/blobs",
                json={"content": content, "encoding": "base64"},
            )
            if resp.status_code not in (201, 200):
                fail(resp, f"blob {rel}")
            tree_entries.append(
                {"path": rel, "mode": "100644", "type": "blob", "sha": resp.json()["sha"]}
            )
            if i % 10 == 0 or i == len(files):
                print(f"  загружено {i}/{len(files)}…")

        tree = client.post(f"/repos/{REPO}/git/trees", json={"tree": tree_entries})
        if tree.status_code not in (201, 200):
            fail(tree, "создание tree")
        tree_sha = tree.json()["sha"]

        commit = client.post(
            f"/repos/{REPO}/git/commits",
            json={
                "message": os.environ.get("COMMIT_MESSAGE", COMMIT_MESSAGE),
                "tree": tree_sha,
                "parents": parents,
            },
        )
        if commit.status_code not in (201, 200):
            fail(commit, "создание коммита")
        commit_sha = commit.json()["sha"]

        if parents:
            upd = client.patch(
                f"/repos/{REPO}/git/refs/heads/{BRANCH}",
                json={"sha": commit_sha, "force": False},
            )
        else:
            upd = client.post(
                f"/repos/{REPO}/git/refs",
                json={"ref": f"refs/heads/{BRANCH}", "sha": commit_sha},
            )
        if upd.status_code not in (200, 201):
            fail(upd, "обновление ветки")

        print()
        print(f"ГОТОВО: https://github.com/{REPO}/commit/{commit_sha}")
        print(f"Репозиторий: https://github.com/{REPO}")


def main() -> None:
    files = collect_files()
    if "--dry-run" in sys.argv:
        total = sum(p.stat().st_size for _, p in files)
        print(f"Репозиторий: {REPO}  ветка: {BRANCH}")
        print(f"Файлов: {len(files)}, объём: {total / 1024:.1f} KB\n")
        for rel, path in files:
            print(f"  {rel:55s} {path.stat().st_size / 1024:7.1f} KB")
        print("\n.env и data/ исключены:", not any(r == ".env" for r, _ in files))
        return

    token = load_token()
    if not token:
        print("Нет токена. Задай GITHUB_TOKEN или github_token.txt")
        sys.exit(1)
    push(token)


if __name__ == "__main__":
    main()
