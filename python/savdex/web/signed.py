"""
Подписанные ссылки — URL::temporarySignedRoute и hasValidSignature Laravel.

Подпись — HMAC-SHA256 адреса без подписи ключом app.key (строкой, как
она записана в APP_KEY, вместе с «base64:»); прежние ключи
(APP_PREVIOUS_KEYS) тоже принимаются. Срок — параметр expires.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from urllib.parse import parse_qsl, quote, urlencode


def _keys() -> list[str]:
    keys = [os.environ.get("APP_KEY") or ""]
    keys += [k.strip() for k in (os.environ.get("APP_PREVIOUS_KEYS") or "").split(",") if k.strip()]

    return [k for k in keys if k]


def _sign(url: str, key: str) -> str:
    return hmac.new(key.encode(), url.encode(), hashlib.sha256).hexdigest()


def temporary(root: str, path: str, minutes: int, query: dict[str, str] | None = None) -> str:
    """URL::temporarySignedRoute: параметры запроса по алфавиту, expires, подпись."""
    params = {**(query or {}), "expires": str(int(time.time()) + minutes * 60)}
    base = root + path + "?" + urlencode(sorted(params.items()), quote_via=quote)
    keys = _keys()
    signature = _sign(base, keys[0]) if keys else ""

    return base + "&signature=" + signature


def valid(url_without_query: str, query_string: str) -> bool:
    """UrlGenerator::hasValidSignature: подпись одним из ключей и срок не вышел."""
    pairs = [p for p in query_string.split("&") if p and not p.startswith("signature=")]
    original = url_without_query + ("?" + "&".join(pairs) if pairs else "")
    given = dict(parse_qsl(query_string)).get("signature", "")

    if not any(hmac.compare_digest(_sign(original, key), given) for key in _keys()):
        return False

    expires = dict(parse_qsl(query_string)).get("expires")

    try:
        return not expires or time.time() <= int(expires)
    except ValueError:
        return False
