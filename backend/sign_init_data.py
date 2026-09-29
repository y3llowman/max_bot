import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import urlencode

from dotenv import load_dotenv

TEST_USER = 9_000_000_000_000_000_001


def sign(max_user_id: int) -> str:
    load_dotenv()
    user = json.dumps({"id": max_user_id, "first_name": "Проверка API", "username": "api_check"}, ensure_ascii=False)
    fields = {"auth_date": str(int(time.time())), "query_id": f"api-check-{max_user_id}", "user": user}
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", os.environ["MAX_TOKEN"].encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


if __name__ == "__main__":
    print(sign(int(sys.argv[1]) if len(sys.argv) > 1 else TEST_USER))
