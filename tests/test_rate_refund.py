import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import Mock, call, patch
from urllib.error import HTTPError

from nexwacli.api import API_URL, APIError, Client, retry_delay
from .test_api import KEY, response
from . import test_orders as order_fixtures


def limited(after=None, body=b'{"error":"Slow down"}'):
    return HTTPError(API_URL, 429, "Rate limit", {"Retry-After": after} if after else {}, io.BytesIO(body))


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.client = Client(KEY)
        self.client.opener = Mock()

    @patch("nexwacli.api.time.sleep")
    def test_read_retries_use_progressive_waits_and_stderr(self, sleep):
        self.client.opener.open.side_effect = [limited(), limited(), response({"balance": "20.00"})]
        with redirect_stderr(io.StringIO()) as notices:
            self.assertEqual(self.client.call("balance")["balance"], "20.00")
        self.assertEqual(sleep.call_args_list, [call(1), call(2)])
        self.assertIn("Waiting 1s", notices.getvalue())
        self.assertEqual(self.client.opener.open.call_count, 3)

    @patch("nexwacli.api.time.sleep")
    def test_seconds_and_http_dates_are_respected(self, sleep):
        self.client.opener.open.side_effect = [limited("18"), response([])]
        with redirect_stderr(io.StringIO()):
            self.assertEqual(self.client.call("services"), [])
        sleep.assert_called_once_with(18)
        with patch("nexwacli.api.time.time", return_value=0):
            self.assertEqual(retry_delay("Thu, 01 Jan 1970 00:00:20 GMT", 0), 20)

    @patch("nexwacli.api.time.sleep")
    def test_long_deadline_and_retry_exhaustion_stop_safely(self, sleep):
        self.client.opener.open.side_effect = [limited("120")]
        with self.assertRaises(APIError) as error:
            self.client.call("status", order=25)
        self.assertEqual(error.exception.retry_after, "120")
        self.assertEqual(self.client.opener.open.call_count, 1)
        sleep.assert_not_called()
        self.client.opener.open.reset_mock()
        self.client.opener.open.side_effect = [limited(), limited(), limited()]
        with redirect_stderr(io.StringIO()), self.assertRaises(APIError):
            self.client.call("balance")
        self.assertEqual(self.client.opener.open.call_count, 3)

    @patch("nexwacli.api.time.sleep")
    def test_mutations_never_retry_even_with_non_json_429(self, sleep):
        for action in ("add", "refill"):
            self.client.opener.open.reset_mock()
            self.client.opener.open.side_effect = [limited("4", b"rate limited")]
            with self.assertRaises(APIError) as error:
                self.client.call(action, idempotency_key="fixture-stable-request")
            self.assertEqual(error.exception.status, 429)
            self.assertEqual(error.exception.retry_after, "4")
            self.assertEqual(self.client.opener.open.call_count, 1)
        sleep.assert_not_called()

    def test_refund_error_remains_an_error_without_automatic_retry(self):
        for message in ("Ordine non eseguito. Rimborso in verifica.", "Servizio momentaneamente non disponibile. Importo riaccreditato."):
            self.client.opener.open.reset_mock()
            self.client.opener.open.side_effect = None
            self.client.opener.open.return_value = response({"error": message})
            with self.assertRaises(APIError) as error:
                self.client.call("add", idempotency_key="fixture-stable-request")
            self.assertEqual(error.exception.server_message, message)
            self.assertEqual(self.client.opener.open.call_count, 1)

    def test_key_and_permission_hints_preserve_server_messages(self):
        for status, hint in ((401, "revoked"), (403, "permissions")):
            self.client.opener.open.return_value = response({"error": "Fixture error"}, status)
            with self.assertRaises(APIError) as error:
                self.client.call("balance")
            self.assertIn(hint, str(error.exception))
            self.assertEqual(error.exception.server_message, "Fixture error")

    def test_malformed_retry_after_uses_bounded_fallback(self):
        for value in (None, "invalid", "-2", "NaN"):
            self.assertEqual(retry_delay(value, 1), 2)
        self.assertGreater(retry_delay("9" * 80, 0), 30)


class RefundJournalTests(unittest.TestCase):
    setUp = order_fixtures.OrderTests.setUp
    args = order_fixtures.OrderTests.args

    def test_pending_refund_keeps_original_key_and_never_saves_success(self):
        self.client.call.side_effect = [order_fixtures.CATALOG, APIError("Rimborso in verifica", 200)]
        with self.assertRaisesRegex(APIError, "Rimborso in verifica"):
            self.app.run(self.args("--yes"))
        record = self.store.request(KEY, "test-1")
        self.assertEqual(record["state"], "pending")
        self.assertFalse(record.get("response"))
        self.client.call.side_effect = APIError("Importo riaccreditato", 200)
        from nexwacli.cli import parser
        with self.assertRaisesRegex(APIError, "Importo riaccreditato"):
            self.app.run(parser().parse_args(["orders", "retry", "test-1", "--yes"]))
        self.assertEqual(self.client.call.call_args.kwargs["idempotency_key"], "test-1")
        self.assertEqual(self.store.request(KEY, "test-1")["state"], "pending")
