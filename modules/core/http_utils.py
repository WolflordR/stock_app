from __future__ import annotations

import json
import ssl
import time
import urllib.request
from urllib.error import HTTPError, URLError


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
}


def _build_insecure_ssl_context():
    insecure_context = ssl.create_default_context()
    insecure_context.check_hostname = False
    insecure_context.verify_mode = ssl.CERT_NONE
    return insecure_context


RETRYABLE_ERROR_TYPES = (URLError, TimeoutError, ssl.SSLError)


def request_bytes(
    url,
    *,
    headers=None,
    timeout=30,
    allow_insecure_fallback=True,
    retries=2,
    retry_delay_sec=0.35,
):
    merged_headers = DEFAULT_HEADERS | (headers or {})
    request = urllib.request.Request(url, headers=merged_headers)
    last_error = None

    for attempt in range(max(1, int(retries) + 1)):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError:
            raise
        except RETRYABLE_ERROR_TYPES as exc:
            last_error = exc
            if allow_insecure_fallback:
                try:
                    with urllib.request.urlopen(
                        request,
                        timeout=timeout,
                        context=_build_insecure_ssl_context(),
                    ) as response:
                        return response.read()
                except HTTPError:
                    raise
                except RETRYABLE_ERROR_TYPES as fallback_exc:
                    last_error = fallback_exc

            if attempt >= int(retries):
                break
            time.sleep(max(0.0, float(retry_delay_sec)) * (attempt + 1))

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request_bytes failed without an exception for {url}")


def request_text(
    url,
    *,
    headers=None,
    timeout=30,
    encoding="utf-8",
    errors="replace",
    allow_insecure_fallback=True,
    retries=2,
    retry_delay_sec=0.35,
):
    raw = request_bytes(
        url,
        headers=headers,
        timeout=timeout,
        allow_insecure_fallback=allow_insecure_fallback,
        retries=retries,
        retry_delay_sec=retry_delay_sec,
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
    retries=2,
    retry_delay_sec=0.35,
):
    return json.loads(
        request_text(
            url,
            headers=headers,
            timeout=timeout,
            encoding=encoding,
            errors=errors,
            allow_insecure_fallback=allow_insecure_fallback,
            retries=retries,
            retry_delay_sec=retry_delay_sec,
        )
    )
