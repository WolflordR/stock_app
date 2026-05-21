from __future__ import annotations

import json
import ssl
import urllib.request


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


def _build_insecure_ssl_context():
    insecure_context = ssl.create_default_context()
    insecure_context.check_hostname = False
    insecure_context.verify_mode = ssl.CERT_NONE
    return insecure_context


def request_bytes(url, *, headers=None, timeout=30, allow_insecure_fallback=True):
    merged_headers = DEFAULT_HEADERS | (headers or {})
    request = urllib.request.Request(url, headers=merged_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception:
        if not allow_insecure_fallback:
            raise
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=_build_insecure_ssl_context(),
        ) as response:
            return response.read()


def request_text(
    url,
    *,
    headers=None,
    timeout=30,
    encoding="utf-8",
    errors="replace",
    allow_insecure_fallback=True,
):
    raw = request_bytes(
        url,
        headers=headers,
        timeout=timeout,
        allow_insecure_fallback=allow_insecure_fallback,
    )
    return raw.decode(encoding, errors=errors)


def request_json(
    url,
    *,
    headers=None,
    timeout=30,
    encoding="utf-8",
    errors="replace",
    allow_insecure_fallback=True,
):
    return json.loads(
        request_text(
            url,
            headers=headers,
            timeout=timeout,
            encoding=encoding,
            errors=errors,
            allow_insecure_fallback=allow_insecure_fallback,
        )
    )
