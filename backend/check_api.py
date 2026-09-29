import subprocess
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main(base: str) -> int:
    spec = yaml.safe_load((ROOT / "DATA-API.yaml").read_text(encoding="utf-8"))
    init_data = subprocess.run([sys.executable, str(Path(__file__).with_name("sign_init_data.py"))],
                               capture_output=True, text=True, check=True).stdout.strip()
    token, task_id, failed = None, None, 0
    with httpx.Client(base_url=base.rstrip("/"), timeout=60) as client:
        for check in spec["checks"]:
            headers = dict(check.get("headers") or {})
            body = check.get("body")
            if isinstance(body, dict) and str(body.get("initData", "")).startswith("<"):
                body = {"initData": init_data}
            if check["role"] == "user":
                headers["Authorization"] = f"Bearer {token}"
            response = client.request(check["method"], check["path"].replace("{task_id}", str(task_id)),
                                      headers=headers, params=check.get("query"), json=body)
            ok, detail = response.status_code in check["expected_status"], ""
            expected = check.get("response")
            if ok and expected and response.status_code != 204:
                data = response.json()
                if expected.get("type") == "array":
                    fields = expected.get("item_required_fields") or []
                    ok = isinstance(data, list) and all(f in data[0] for f in fields if data)
                else:
                    missing = [f for f in expected.get("required_fields", []) if f not in data]
                    ok, detail = not missing, f"нет полей: {missing}" if missing else ""
                if check["id"] == "auth" and ok:
                    token = data["access_token"]
                if check["id"] == "calendar" and ok and data:
                    task_id = data[0]["id"]
            failed += not ok
            print("OK  " if ok else "FAIL", check["id"], response.status_code, detail)
    print("провалено проверок:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"))
