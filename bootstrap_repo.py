# Бутстрап пустой репы: первый коммит через contents API (blobs API на пустой репе 409).
import base64
from pathlib import Path

import httpx

token = Path(__file__).resolve().parent.joinpath("github_token.txt").read_text(encoding="utf-8").strip()
H = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
repo = "CryptoPassApp/CryptoPassApp-AML"
readme = Path(__file__).resolve().parent / "README.md"

with httpx.Client(timeout=30, headers=H) as c:
    r = c.put(
        f"https://api.github.com/repos/{repo}/contents/README.md",
        json={
            "message": "init: CryptoPassApp AML scanner",
            "content": base64.b64encode(readme.read_bytes()).decode(),
        },
    )
    print("bootstrap README:", r.status_code)
    if r.status_code not in (200, 201):
        print(r.text[:300])
