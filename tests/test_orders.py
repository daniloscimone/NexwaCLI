from contextlib import redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from nexwacli.api import APIError, NexwaError
from nexwacli.cli import App, parser, target_url
from nexwacli.storage import Store
from .test_api import KEY

CATALOG = [{"service": 12, "name": "Example service", "platform": "instagram", "min": 10, "max": 1000, "rate": "3.00", "price_per_item": "0.01", "pricing_unit": "per_1000", "currency": "EUR", "refill": True}]


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.client = Mock(key=KEY)
        self.app = App(self.store, client_factory=lambda *a, **k: self.client)
        env = patch.dict(os.environ, {"NEXWA_API_KEY": KEY})
        env.start()
        self.addCleanup(env.stop)
        self.out = redirect_stdout(io.StringIO())
        self.err = redirect_stderr(io.StringIO())
        self.out.__enter__()
        self.err.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)
        self.addCleanup(self.err.__exit__, None, None, None)

    def args(self, *extra):
        return parser().parse_args(["orders", "create", "--service", "12", "--quantity", "100", "--link", "https://instagram.com/example/", "--request-key", "test-1", *extra])

    def test_journal_exists_before_spending_credit(self):
        def call(action, **params):
            if action == "services":
                return CATALOG
            record = self.store.request(KEY, "test-1")
            self.assertEqual(record["state"], "pending")
            self.assertEqual(record["params"]["quantity"], 100)
            self.assertEqual(params["idempotency_key"], "test-1")
            return {"order": 25, "charge": "0.50", "currency": "EUR"}
        self.client.call.side_effect = call
        result = self.app.run(self.args("--yes"))
        self.assertEqual(result["charge"], "0.50")
        self.assertEqual(self.store.request(KEY, "test-1")["state"], "accepted")

    def test_timeout_then_retry_uses_original_payload_and_key(self):
        self.client.call.side_effect = [CATALOG, APIError("timeout")]
        with self.assertRaises(APIError):
            self.app.run(self.args("--yes"))
        self.assertEqual(self.store.request(KEY, "test-1")["state"], "pending")
        self.client.call.side_effect = None
        self.client.call.return_value = {"order": 25, "duplicate": True}
        result = self.app.run(parser().parse_args(["orders", "retry", "test-1", "--yes"]))
        self.assertTrue(result["duplicate"])
        self.assertEqual(self.client.call.call_args.kwargs["idempotency_key"], "test-1")
        self.assertEqual(self.client.call.call_args.kwargs["quantity"], 100)

    def test_successful_local_replay_makes_no_second_request(self):
        self.client.call.side_effect = [CATALOG, {"order": 25}]
        self.app.run(self.args("--yes"))
        self.client.call.reset_mock()
        result = self.app.run(self.args("--yes"))
        self.assertTrue(result["local_replay"])
        self.client.call.assert_not_called()

    def test_request_key_cannot_be_reused_for_different_payload(self):
        self.client.call.side_effect = [CATALOG, {"order": 25}]
        self.app.run(self.args("--yes"))
        changed = self.args("--yes")
        changed.quantity = 101
        with self.assertRaisesRegex(NexwaError, "different purchase"):
            self.app.run(changed)

    def test_dry_run_never_submits_or_journals_purchase(self):
        self.client.call.return_value = CATALOG
        result = self.app.run(self.args("--dry-run"))
        self.assertTrue(result["dry_run"])
        self.assertIsNone(self.store.request(KEY, "test-1"))
        self.assertEqual(self.client.call.call_count, 1)
        self.assertEqual(self.client.call.call_args.args, ("services",))

    def test_quantity_outside_catalog_limits_never_orders(self):
        self.client.call.return_value = CATALOG
        args = self.args("--yes")
        args.quantity = 1001
        with self.assertRaisesRegex(NexwaError, "between 10 and 1000"):
            self.app.run(args)
        self.assertEqual(self.client.call.call_count, 1)

    def test_noninteractive_purchase_needs_confirmation(self):
        self.client.call.return_value = CATALOG
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(NexwaError, "Confirmation required"):
                self.app.run(self.args())
        self.assertIsNone(self.store.request(KEY, "test-1"))

    def test_disk_failure_prevents_submission(self):
        self.client.call.return_value = CATALOG
        with patch.object(self.store, "save_request", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.app.run(self.args("--yes"))
        self.assertEqual(self.client.call.call_count, 1)

    def test_lock_blocks_concurrent_submission(self):
        with self.store.lock(KEY, "test-1"):
            with self.assertRaisesRegex(NexwaError, "locked"):
                self.app.run(self.args("--yes"))
        self.client.call.assert_not_called()

    def test_history_is_isolated_by_customer_key(self):
        self.client.call.side_effect = [CATALOG, {"order": 25}]
        self.app.run(self.args("--yes"))
        other_key = "nxw_live_" + "b" * 43
        self.assertEqual(self.store.history(other_key), [])
        self.assertEqual(len(self.store.history(KEY)), 1)
        text = "".join(p.read_text() for p in Path(self.temp.name).rglob("*.json"))
        self.assertNotIn(KEY, text)

    def test_status_ids_are_validated_before_request(self):
        for ids in (["1junk"], ["1,,2"], [str(i) for i in range(1, 102)]):
            with self.assertRaises(NexwaError):
                self.app.run(parser().parse_args(["orders", "status", *ids]))
        self.client.call.assert_not_called()

    def test_status_supports_spaces_commas_and_deduplication(self):
        self.client.call.return_value = {"1": {"status": "Completed"}, "2": {"error": "Order not found"}}
        result = self.app.run(parser().parse_args(["orders", "status", "1,2", "2"]))
        self.client.call.assert_called_once_with("status", orders="1,2")
        self.assertIn("error", result["2"])

    def test_target_url_validation(self):
        for url in ("file:///tmp/test", "https://user:password@example.com", "https://example.com/a b", "https://example.com:bad", "https://"):
            with self.assertRaises(NexwaError):
                target_url(url)

    def test_json_option_works_at_every_level(self):
        for argv in (["--json", "balance"], ["balance", "--json"], ["orders", "--json", "list"], ["orders", "list", "--json"]):
            self.assertTrue(parser().parse_args(argv).json)

    def test_catalog_cache_and_explicit_refresh(self):
        self.client.call.return_value = CATALOG
        self.store.catalog(self.client)
        self.store.catalog(self.client)
        self.assertEqual(self.client.call.call_count, 1)
        self.store.catalog(self.client, refresh=True)
        self.assertEqual(self.client.call.call_count, 2)

    def test_logout_removes_saved_key_without_deleting_receipts(self):
        self.store.save_key(KEY)
        if os.name != "nt":
            self.assertEqual(self.store.config_path.stat().st_mode & 0o777, 0o600)
        self.store.logout()
        self.assertEqual(self.store.saved_key(), "")
