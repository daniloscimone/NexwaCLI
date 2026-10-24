import io
import json
from pathlib import Path
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

from nexwacli.api import API_URL, APIError, Client, NoRedirects, NexwaError, tls_context

KEY = "nxw_live_" + "a" * 43


def response(data, code=200, headers=None):
    result = io.BytesIO(json.dumps(data).encode())
    result.code = code
    result.headers = headers or {}
    return result


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.client = Client(KEY)
        self.client.opener = Mock()

    def test_uses_only_nexwa_https_and_authorization_header(self):
        self.client.opener.open.return_value = response({"order": 25, "charge": "2.00", "currency": "EUR"})
        result = self.client.call("add", service=12, quantity=100, link="https://example.com/a?b=1&c=2", idempotency_key="customer-15")
        sent = self.client.opener.open.call_args.args[0]
        self.assertEqual(sent.full_url, API_URL)
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(sent.get_header("Authorization"), f"Bearer {KEY}")
        body = parse_qs(sent.data.decode())
        self.assertNotIn("key", body)
        self.assertEqual(body["link"], ["https://example.com/a?b=1&c=2"])
        self.assertEqual(body["idempotency_key"], ["customer-15"])
        self.assertEqual(result["charge"], "2.00")

    def test_http_200_application_error_is_failure(self):
        self.client.opener.open.return_value = response({"error": "Insufficient balance"})
        with self.assertRaisesRegex(APIError, "Insufficient balance"):
            self.client.call("add")

    def test_429_preserves_retry_after_and_does_not_retry(self):
        self.client.opener.open.side_effect = HTTPError(API_URL, 429, "Too many requests", {"Retry-After": "18"}, io.BytesIO(b'{"error":"Slow down"}'))
        with self.assertRaises(APIError) as caught:
            self.client.call("services")
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(caught.exception.retry_after, "18")
        self.assertEqual(self.client.opener.open.call_count, 1)

    def test_network_error_does_not_repeat_purchase(self):
        self.client.opener.open.side_effect = URLError("offline")
        with self.assertRaisesRegex(APIError, "outcome may be unknown"):
            self.client.call("add")
        self.assertEqual(self.client.opener.open.call_count, 1)

    def test_invalid_json_has_no_raw_body_in_error(self):
        raw = io.BytesIO(b"<html>private data</html>")
        raw.code, raw.headers = 502, {}
        self.client.opener.open.return_value = raw
        with self.assertRaisesRegex(APIError, "non-JSON") as caught:
            self.client.call("balance")
        self.assertNotIn("private data", str(caught.exception))

    def test_invalid_success_shape_is_not_accepted(self):
        self.client.opener.open.return_value = response({"unexpected": True})
        with self.assertRaisesRegex(APIError, "invalid add response"):
            self.client.call("add")

    def test_secret_in_api_error_is_redacted(self):
        self.client.opener.open.return_value = response({"error": f"Rejected {KEY}"})
        with self.assertRaises(APIError) as caught:
            self.client.call("balance")
        self.assertNotIn(KEY, str(caught.exception))

    def test_redirects_are_blocked(self):
        self.assertIsNone(NoRedirects().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_rejects_bad_keys_and_timeouts(self):
        for key in ("bad", KEY + "\nInjected: value"):
            with self.assertRaises(NexwaError):
                Client(key)
        for timeout in (0, 301, float("nan"), float("inf")):
            with self.assertRaises(NexwaError):
                Client(KEY, timeout=timeout)

    def test_unpublished_actions_are_rejected(self):
        with self.assertRaises(NexwaError):
            self.client.call("cancel", order=25)
        self.client.opener.open.assert_not_called()

    def test_tls_keeps_hostname_and_certificate_verification_enabled(self):
        context = tls_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_tls_uses_system_bundle_when_build_machine_path_is_missing(self):
        context = Mock()
        context.cert_store_stats.return_value = {"x509_ca": 0}
        with patch("nexwacli.api.ssl.create_default_context", return_value=context), patch("nexwacli.api.Path.is_file", return_value=True):
            self.assertIs(tls_context(), context)
        context.load_verify_locations.assert_called_once_with(cafile=str(Path("/etc/ssl/cert.pem")))
