"""Small HTTPS client for the five published Nexwa API actions."""

import http.client
import json
import math
from pathlib import Path
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from . import __version__

API_URL = "https://nexwa.store/api/v2"
ACCOUNT_URL = "https://nexwa.store/account.html"
MAX_RESPONSE = 8 * 1024 * 1024


class NexwaError(Exception):
    """An error suitable for display without a traceback."""

    def __init__(self, message, message_code=None, **values):
        super().__init__(message)
        self.message_code = message_code
        self.values = values


class APIError(NexwaError):
    def __init__(self, message, status=None, retry_after=None, message_code=None, server_message=None):
        super().__init__(message, message_code)
        self.status = status
        self.retry_after = retry_after
        self.server_message = server_message


class NoRedirects(HTTPRedirectHandler):
    # Never forward a customer's Authorization header to another location.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def tls_context():
    context = ssl.create_default_context()
    # A standalone Python build can retain a certificate path from its build
    # machine. Fall back to the OS trust bundle, keeping verification enabled.
    if context.cert_store_stats()["x509_ca"] == 0:
        for name in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
            path = Path(name)
            if path.is_file():
                context.load_verify_locations(cafile=str(path))
                break
    return context


def validate_key(key):
    key = key.strip()
    if not key.startswith("nxw_live_") or not 28 <= len(key) <= 128:
        raise NexwaError("Enter a customer API key generated in Nexwa > Wallet and API.", "invalid_key")
    if any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in key):
        raise NexwaError("The API key contains invalid characters.", "invalid_key")
    return key


class Client:
    def __init__(self, key, timeout=30):
        self.key = validate_key(key)
        if not math.isfinite(timeout) or not 1 <= timeout <= 300:
            raise NexwaError("Timeout must be between 1 and 300 seconds.")
        self.timeout = timeout
        try:
            self.opener = build_opener(NoRedirects(), HTTPSHandler(context=tls_context()))
        except OSError:
            raise APIError("Could not load system TLS certificates. Check your Python certificate setup.", message_code="network_error") from None

    def call(self, action, **params):
        if action not in {"balance", "services", "add", "status", "refill"}:
            raise NexwaError("Unsupported Nexwa API action.")
        request = Request(
            API_URL,
            data=urlencode({"action": action, **params}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": f"NexwaCLI/{__version__}",
            },
            method="POST",
        )
        # Purchases and refill requests are never retried automatically.
        try:
            try:
                response = self.opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                response = exc
            with response:
                status = response.code
                retry_after = response.headers.get("Retry-After")
                raw = response.read(MAX_RESPONSE + 1)
        except (URLError, OSError, socket.timeout, ssl.SSLError, http.client.HTTPException):
            raise APIError(
                "Could not complete the Nexwa request. Check your connection and TLS certificates. "
                "If you were placing an order, its outcome may be unknown; keep the same request key.",
                message_code="network_error",
            ) from None
        if len(raw) > MAX_RESPONSE:
            raise APIError("Nexwa returned a response larger than 8 MiB.", status, message_code="invalid_response")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise APIError(f"Nexwa returned a non-JSON response (HTTP {status}).", status, message_code="invalid_response") from None
        if not 200 <= status < 300 or (isinstance(data, dict) and "error" in data):
            message = str(data.get("error", f"Request failed (HTTP {status}).")) if isinstance(data, dict) else f"Request failed (HTTP {status})."
            message = message.replace(self.key, "[redacted]")
            server_message = message
            if status == 401:
                message += " Generate or check your customer API key on nexwa.store."
            elif status == 403:
                message += " Check that your Nexwa account email is verified."
            elif status == 429:
                message += f" Rate limit reached. Retry-After: {retry_after or 'not provided'}."
            raise APIError(message, status, retry_after, server_message=server_message)
        if action == "services":
            if not isinstance(data, list) or any(not isinstance(s, dict) or "service" not in s for s in data):
                raise APIError("Nexwa returned an invalid service catalog.", status, message_code="invalid_response")
        else:
            required = {"balance": "balance", "add": "order", "refill": "refill"}.get(action)
            if not isinstance(data, dict) or (required and required not in data):
                raise APIError(f"Nexwa returned an invalid {action} response.", status, message_code="invalid_response")
        return data
