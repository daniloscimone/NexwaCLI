from contextlib import redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
from string import Formatter
import tempfile
import unittest
from unittest.mock import Mock, patch

from nexwacli.cli import App, main, parser
from nexwacli.api import APIError, NexwaError, validate_key
from nexwacli.i18n import LANGUAGES, MESSAGES, Translator
from nexwacli.panel import Panel, Terminal
from nexwacli.storage import Store
from .test_api import KEY
from .test_orders import CATALOG


class TranslationTests(unittest.TestCase):
    def test_every_translation_has_all_languages_and_matching_placeholders(self):
        for key, translations in MESSAGES.items():
            self.assertEqual(len(translations), len(LANGUAGES), key)
            fields = [{field for _, field, _, _ in Formatter().parse(text) if field is not None} for text in translations]
            self.assertTrue(all(fields[0] == other for other in fields), key)
            self.assertTrue(all(text.strip() for text in translations), key)

    def test_confirmation_accepts_localized_yes_without_accepting_empty_input(self):
        for language in LANGUAGES:
            translator = Translator(language)
            self.assertTrue(translator.agrees(translator("yes")))
            self.assertFalse(translator.agrees(""))
            self.assertFalse(translator.agrees(translator("no")))


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.client = Mock(key=KEY)
        self.app = App(self.store, client_factory=lambda *a, **k: self.client)
        self.client.call.side_effect = lambda action, **params: CATALOG if action == "services" else {"balance": "12.50", "currency": "EUR"} if action == "balance" else {"order": 88, "charge": "0.50", "currency": "EUR"}
        env = patch.dict(os.environ, {"NEXWA_API_KEY": KEY, "NO_COLOR": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.output = io.StringIO()
        out = redirect_stdout(self.output)
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def test_language_change_persists_and_updates_current_panel(self):
        panel = Panel(self.app)
        with patch("builtins.input", side_effect=["1", "2", "0"]):
            panel.settings()
        self.assertEqual(panel.t.language, "it")
        self.assertEqual(Store(self.temp.name).settings()["language"], "it")
        self.assertIn("Impostazioni", self.output.getvalue())

    def test_dashboard_uses_real_balance_and_local_receipt_count(self):
        panel = Panel(self.app)
        panel.home()
        panel.home()
        self.assertIn("12.50 EUR", self.output.getvalue())
        self.assertIn("Local receipts: 0", self.output.getvalue())
        self.assertEqual(self.client.call.call_count, 1)

    def test_disconnected_dashboard_does_not_make_api_requests(self):
        with patch.dict(os.environ, {"NEXWA_API_KEY": ""}):
            Panel(self.app).home()
        self.assertIn("Not connected", self.output.getvalue())
        self.client.call.assert_not_called()

    def test_no_color_suppresses_escape_sequences_even_on_tty(self):
        with patch("sys.stdout.isatty", return_value=True):
            terminal = Terminal("on")
            terminal.heading("Settings")
        self.assertNotIn("\033", self.output.getvalue())

    def test_long_hostile_catalog_text_wraps_without_terminal_controls(self):
        panel = Panel(self.app)
        hostile = {**CATALOG[0], "name": "\033[2J" + "Long service " * 40}
        with patch("shutil.get_terminal_size", return_value=os.terminal_size((40, 24))):
            panel.detail(hostile)
        text = self.output.getvalue()
        self.assertNotIn("\033", text)
        self.assertTrue(all(len(line) <= 40 for line in text.splitlines()))

    def test_purchase_cancel_never_sends_add(self):
        panel = Panel(self.app)
        with patch("builtins.input", side_effect=["https://instagram.com/example/", "100", "", ""]):
            panel.purchase(CATALOG[0])
        self.assertNotIn("add", [c.args[0] for c in self.client.call.call_args_list])
        self.assertEqual(self.store.history(KEY), [])

    def test_confirmed_purchase_saves_receipt_and_shows_order_id(self):
        panel = Panel(self.app)
        with patch("builtins.input", side_effect=["https://instagram.com/example/", "100", "yes", ""]):
            panel.purchase(CATALOG[0])
        records = self.store.history(KEY)
        self.assertEqual(records[0]["response"]["order"], 88)
        self.assertIn("Order ID: 88", self.output.getvalue())
        self.assertEqual([c.args[0] for c in self.client.call.call_args_list].count("add"), 1)

    def test_italian_purchase_confirmation_and_receipt(self):
        self.store.save_settings(language="it")
        panel = Panel(self.app)
        with patch("builtins.input", side_effect=["https://instagram.com/example/", "100", "sì", ""]):
            panel.purchase(CATALOG[0])
        self.assertIn("Ordine accettato", self.output.getvalue())

    def test_panel_settings_command_does_not_require_credentials(self):
        with patch.dict(os.environ, {"NEXWA_API_KEY": ""}):
            result = self.app.run(parser().parse_args(["settings", "--language", "ru", "--color", "off"]))
        self.assertEqual(result, {"language": "ru", "color": "off"})
        self.client.call.assert_not_called()

    def test_json_runtime_error_has_no_stdout(self):
        error = io.StringIO()
        with patch.dict(os.environ, {"NEXWA_API_KEY": "", "NEXWA_CONFIG_DIR": self.temp.name}), redirect_stderr(error):
            result = main(["balance", "--json"])
        self.assertEqual(result, 1)
        self.assertEqual(self.output.getvalue(), "")
        self.assertIn('"error":', error.getvalue())

    def test_json_purchase_confirmation_keeps_stdout_machine_readable(self):
        from nexwacli.cli import confirm

        error = io.StringIO()
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="yes"), redirect_stderr(error):
            confirm("Confirm purchase?")
        self.assertEqual(self.output.getvalue(), "")
        self.assertIn("Confirm purchase?", error.getvalue())

    def test_ascii_rules_for_legacy_encoding(self):
        with patch("sys.stdout") as stdout:
            stdout.encoding = "ascii"
            self.assertEqual(Terminal().rule_char, "-")

    def test_italian_invalid_key_error_is_localized(self):
        self.store.save_settings(language="it")
        panel = Panel(self.app)
        with self.assertRaises(NexwaError) as caught:
            validate_key("invalid")
        self.assertIn("chiave API cliente valida", panel.error_text(caught.exception))
        self.assertNotIn("Use a valid", panel.error_text(caught.exception))

    def test_italian_network_failure_error_is_localized(self):
        from urllib.error import URLError
        from nexwacli.api import Client

        self.store.save_settings(language="it")
        panel = Panel(self.app)
        client = Client(KEY)
        client.opener = Mock()
        client.opener.open.side_effect = URLError("offline")
        with self.assertRaises(APIError) as caught:
            client.call("balance")
        self.assertIn("Connessione non riuscita", panel.error_text(caught.exception))

    def test_original_server_message_is_preserved_with_translated_hint(self):
        self.store.save_settings(language="fr")
        panel = Panel(self.app)
        error = APIError("Raw API error plus English hint", 403, server_message="EMAIL_NOT_VERIFIED")
        result = panel.error_text(error)
        self.assertIn("EMAIL_NOT_VERIFIED", result)
        self.assertIn("Vérifiez", result)
        self.assertNotIn("English hint", result)


if __name__ == "__main__":
    unittest.main()
