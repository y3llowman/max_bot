import argparse
import json
import re
import sys
from typing import Any

import requests

CAPTCHA_KEYWORDS = [
    "captcha", "recaptcha", "hcaptcha", "turnstile",
    "g-recaptcha", "cf-chl", "cf_chl", "challenge-platform",
    "verify you are human", "are you a robot", "checking your browser",
    "please enable javascript and cookies", "attention required",
    "ddos protection", "just a moment",
]

CAPTCHA_HTML_PATTERNS = [
    r'class=["\'][^"\']*g-recaptcha',
    r'class=["\'][^"\']*h-captcha',
    r'class=["\'][^"\']*cf-turnstile',
    r'data-sitekey=["\']',
    r'https://www\.google\.com/recaptcha/api\.js',
    r'https://js\.hcaptcha\.com',
    r'https://challenges\.cloudflare\.com',
]

CAPTCHA_JSON_KEYS = [
    "captcha", "captcha_required", "captcha_url", "captcha_token",
    "challenge", "challenge_required", "recaptcha", "hcaptcha",
    "verification_required", "human_verification",
]

SUSPICIOUS_STATUSES = {403, 429, 503}


def analyze_response(resp: requests.Response) -> dict[str, Any]:
    result = {
        "status_code": resp.status_code,
        "url": resp.url,
        "content_type": resp.headers.get("Content-Type", ""),
        "signals": [],
        "is_captcha": False,
        "confidence": 0,
    }

    text = resp.text or ""
    text_lower = text.lower()
    headers_lower = {k.lower(): v.lower() for k, v in resp.headers.items()}

    if resp.status_code in SUSPICIOUS_STATUSES:
        result["signals"].append(f"Подозрительный HTTP-статус: {resp.status_code}")
        result["confidence"] += 20

    if "cf-mitigated" in headers_lower and "challenge" in headers_lower["cf-mitigated"]:
        result["signals"].append("Cloudflare challenge (cf-mitigated)")
        result["confidence"] += 60

    if "x-captcha" in headers_lower or "x-recaptcha" in headers_lower:
        result["signals"].append(f"Заголовок X-Captcha: {headers_lower}")
        result["confidence"] += 50

    if "server" in headers_lower and "cloudflare" in headers_lower["server"]:
        if resp.status_code in SUSPICIOUS_STATUSES:
            result["signals"].append("Cloudflare + подозрительный статус")
            result["confidence"] += 15

    found_keywords = sorted({kw for kw in CAPTCHA_KEYWORDS if kw in text_lower})
    if found_keywords:
        result["signals"].append(f"Ключевые слова: {found_keywords}")
        result["confidence"] += 15 * len(found_keywords)

    found_html = []
    for pat in CAPTCHA_HTML_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            found_html.append(pat)
    if found_html:
        result["signals"].append(f"HTML-паттерны капчи: {found_html}")
        result["confidence"] += 25 * len(found_html)

    if "application/json" in result["content_type"]:
        try:
            data = resp.json()
            found_keys = _find_json_keys(data, CAPTCHA_JSON_KEYS)
            if found_keys:
                result["signals"].append(f"JSON-ключи: {found_keys}")
                result["confidence"] += 30 * len(found_keys)
        except (json.JSONDecodeError, ValueError):
            pass

    result["confidence"] = min(result["confidence"], 100)
    result["is_captcha"] = result["confidence"] >= 30
    return result


def _find_json_keys(obj: Any, keys: list[str], prefix: str = "") -> list[str]:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if k.lower() in keys:
                found.append(path)
            found.extend(_find_json_keys(v, keys, path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(_find_json_keys(item, keys, f"{prefix}[{i}]"))
    return found


def check_url(method: str, url: str, headers: dict, data: str | None,
              timeout: float, allow_redirects: bool) -> dict[str, Any]:
    kwargs = {
        "headers": headers,
        "timeout": timeout,
        "allow_redirects": allow_redirects,
    }
    if data is not None:
        kwargs["data"] = data

    try:
        resp = requests.request(method, url, **kwargs)
        return analyze_response(resp)
    except requests.exceptions.RequestException as e:
        return {
            "status_code": None,
            "url": url,
            "error": str(e),
            "signals": [f"Ошибка запроса: {type(e).__name__}: {e}"],
            "is_captcha": False,
            "confidence": 0,
        }


def print_report(result: dict[str, Any]) -> None:
    print("=" * 60)
    print(f"URL:          {result['url']}")
    print(f"HTTP-статус:  {result.get('status_code')}")
    if "error" in result:
        print(f"Ошибка:       {result['error']}")
    print(f"Капча:        {'ДА' if result['is_captcha'] else 'нет'}")
    print(f"Уверенность:  {result['confidence']}%")
    print("Признаки:")
    if result["signals"]:
        for s in result["signals"]:
            print(f"  • {s}")
    else:
        print("  — нет")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Проверка капчи на API-эндпоинте")
    parser.add_argument("url", help="URL для проверки")
    parser.add_argument("-X", "--method", default="GET", help="HTTP-метод (default: GET)")
    parser.add_argument("-H", "--header", action="append", default=[],
                        help="Заголовок в формате 'Key: Value' (можно несколько)")
    parser.add_argument("-d", "--data", default=None, help="Тело запроса")
    parser.add_argument("-t", "--timeout", type=float, default=10.0, help="Таймаут в секундах")
    parser.add_argument("--no-redirects", action="store_true",
                        help="Не следовать редиректам (полезно для Cloudflare)")
    parser.add_argument("--json", action="store_true", help="Вывод в JSON")

    args = parser.parse_args()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://proverki.gov.ru/",
    }

    result = check_url(
        method=args.method.upper(),
        url=args.url,
        headers=headers,
        data=args.data,
        timeout=args.timeout,
        allow_redirects=not args.no_redirects,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result)

    sys.exit(1 if result["is_captcha"] else 0)


if __name__ == "__main__":
    main()