"""Nexwa customer dashboard. Ordinary terminal input, no runtime dependencies."""

import getpass
import math
import os
import shutil
import sys
import textwrap
import time
import uuid
import webbrowser

from . import __version__
from .api import ACCOUNT_URL, APIError, NexwaError, validate_key
from .i18n import LANGUAGES, Translator
from .storage import timestamp

TOKENS = {
    "brand": (104, 0, 222),
    "accent": (185, 138, 255),
    "success": (134, 215, 161),
    "warning": (237, 197, 117),
    "danger": (255, 161, 174),
}


def safe(value):
    return "".join(c if c.isprintable() else " " for c in str(value))


def enable_windows_ansi():
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        return bool(kernel.GetConsoleMode(handle, ctypes.byref(mode)) and kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except (AttributeError, OSError):
        return False


class Terminal:
    def __init__(self, color="auto"):
        capable = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
        self.color = capable and "NO_COLOR" not in os.environ and color != "off" and enable_windows_ansi()
        try:
            "─".encode(sys.stdout.encoding or "utf-8")
            self.rule_char = "─"
        except UnicodeEncodeError:
            self.rule_char = "-"

    @property
    def width(self):
        return max(16, min(104, shutil.get_terminal_size((88, 24)).columns - 4))

    def ink(self, text, token="accent", bold=False):
        text = safe(text)
        if not self.color:
            return text
        r, g, b = TOKENS[token]
        return f"\033[{('1;' if bold else '')}38;2;{r};{g};{b}m{text}\033[0m"

    def line(self, text="", token=None):
        lines = textwrap.wrap(safe(text), self.width, replace_whitespace=True, break_long_words=True, break_on_hyphens=False) or [""]
        for line in lines:
            print("  " + (self.ink(line, token) if token else line))

    def heading(self, title):
        if self.color:
            print("\033[2J\033[H", end="")
        print()
        wordmark = " NEXWA "
        if self.color:
            r, g, b = TOKENS["brand"]
            wordmark = f"\033[1;97;48;2;{r};{g};{b}m{wordmark}\033[0m"
        print(f"  {wordmark}  CLI {__version__}")
        self.line(self.rule_char * self.width, "accent")
        self.line(title, "accent")
        print()

    def choice(self, key, label, primary=False):
        print("  " + self.ink(f"[{key}]", "accent", primary) + " " + safe(label))


class Panel:
    def __init__(self, app):
        self.app = app
        self.balance = None
        self.balance_at = 0
        self.balance_error = None
        self.configure()

    def configure(self):
        settings = self.app.store.settings()
        self.t = Translator(settings.get("language", "en"))
        self.ui = Terminal(settings.get("color", "auto"))

    def ask(self, key, **values):
        return input("\n  " + self.t(key, **values) + ": ").strip()

    def pause(self):
        input("\n  " + self.t("pause") + ". ")

    def confirm(self, key):
        self.ui.line(self.t(key), "warning")
        return self.t.agrees(self.ask("confirm_hint"))

    def error_text(self, error):
        if isinstance(error, NexwaError) and error.message_code:
            return self.t(error.message_code, **error.values)
        if isinstance(error, APIError) and error.server_message:
            hint = {401: "key_help", 403: "verify_email", 429: "rate_limited"}.get(error.status)
            return error.server_message + (" " + self.t(hint, seconds=error.retry_after or self.t("unknown")) if hint else "")
        return str(error)

    def receipt_warning(self):
        self.ui.line(self.t("receipt_not_saved"), "warning")

    def client(self):
        try:
            key = self.app.key()
        except NexwaError:
            raise NexwaError(self.t("key_help")) from None
        return self.app.client_factory(key, timeout=30)

    def number(self, text):
        if len(text) > 16 or not text.isascii() or not text.isdigit() or not 1 <= int(text) <= 9007199254740991:
            raise NexwaError(self.t("integer"))
        return int(text)

    def home(self):
        self.ui.heading(self.t("dashboard"))
        try:
            client = self.client()
        except NexwaError:
            client = None
        if client is None:
            self.ui.line(self.t("not_connected"), "warning")
            self.ui.line(self.t("welcome"))
        else:
            if time.monotonic() - self.balance_at > 60:
                self.ui.line(self.t("loading"))
                try:
                    self.balance = client.call("balance")
                    self.balance_error = None
                except NexwaError as exc:
                    self.balance, self.balance_error = None, exc
                self.balance_at = time.monotonic()
            if self.balance:
                self.ui.line(self.t("connected") + "  /  nexwa.store", "success")
                self.ui.line(f"{self.t('balance')}    {self.balance['balance']} {self.balance.get('currency', 'EUR')}")
            else:
                self.ui.line(self.t("balance") + "  /  " + self.t("unavailable"), "warning")
                self.ui.line(f"{self.t('error')}: {self.error_text(self.balance_error)}")
            receipts = self.app.store.history(client.key)
            pending = sum(not r.get("response") for r in receipts)
            self.ui.line(f"{self.t('local_orders')}: {len(receipts)}    /    {self.t('pending')}: {pending}")
        print()
        for key, label in (("1", "new_order"), ("2", "services"), ("3", "orders"), ("4", "balance"), ("5", "wallet"), ("6", "settings"), ("7", "connect"), ("0", "exit")):
            self.ui.choice(key, self.t(label), key == "1")

    def login(self):
        self.ui.heading(self.t("connect"))
        self.ui.line(self.t("key_help"))
        self.ui.line(self.t("key_storage"), "warning")
        key = validate_key(getpass.getpass("\n  " + self.t("api_key") + ": "))
        self.ui.line(self.t("loading"))
        self.app.client_factory(key, timeout=30).call("balance")
        self.app.store.save_key(key)
        self.balance_at = 0
        self.ui.line(self.t("account_saved"), "success")
        if os.environ.get("NEXWA_API_KEY"):
            self.ui.line(self.t("env_active"), "warning")
        self.pause()

    def settings(self):
        while True:
            self.ui.heading(self.t("settings"))
            settings = self.app.store.settings()
            self.ui.choice("1", f"{self.t('language')}  /  {LANGUAGES[self.t.language]}")
            self.ui.choice("2", f"{self.t('appearance')}  /  {self.t(settings.get('color', 'auto'))}")
            self.ui.choice("3", self.t("remove_key"))
            self.ui.choice("0", self.t("back"))
            choice = self.ask("choose")
            if choice == "0":
                return
            if choice == "1":
                print()
                for i, (code, name) in enumerate(LANGUAGES.items(), 1):
                    self.ui.choice(str(i), f"{name} ({code})")
                selected = self.ask("choose")
                if selected in {str(i) for i in range(1, 7)}:
                    self.app.store.save_settings(language=list(LANGUAGES)[int(selected) - 1])
            elif choice == "2":
                for i, code in enumerate(("auto", "on", "off"), 1):
                    self.ui.choice(str(i), self.t(code))
                selected = self.ask("choose")
                if selected in {"1", "2", "3"}:
                    self.app.store.save_settings(color=("auto", "on", "off")[int(selected) - 1])
            elif choice == "3":
                if self.confirm("remove_confirm"):
                    self.app.store.logout()
                    self.balance_at = 0
                    self.ui.line(self.t("removed"), "success")
                    if os.environ.get("NEXWA_API_KEY"):
                        self.ui.line(self.t("env_active"), "warning")
                    self.pause()
            else:
                self.ui.line(self.t("invalid_choice"), "warning")
            self.configure()

    def detail(self, service):
        self.ui.heading(f"#{service['service']}  /  {service.get('name', '')}")
        currency = service.get("currency", "EUR")
        for key, value in (("platform", service.get("platform", "")), ("category", service.get("category", "")), ("description", service.get("description") or "—"), ("rate", f"{service.get('rate', '—')} {currency}"), ("per_item", f"{service.get('price_per_item', '—')} {currency}"), ("pricing_unit", service.get("pricing_unit", "—")), ("limits", f"{service.get('min')} – {service.get('max')}"), ("refill_available", self.t("yes" if service.get("refill") else "no"))):
            self.ui.line(f"{self.t(key)}: {value}")
        print()
        self.ui.line(self.t("price_note"), "warning")

    def browse(self, select=False):
        client = self.client()
        self.ui.heading(self.t("services"))
        search = self.ask("search").casefold()
        page, refresh = 0, False
        while True:
            services = self.app.store.catalog(client, refresh=refresh)
            refresh = False
            matches = [s for s in services if search in " ".join(str(s.get(k, "")) for k in ("name", "platform", "category", "description")).casefold()]
            pages = max(1, math.ceil(len(matches) / 6))
            page = min(page, pages - 1)
            self.ui.heading(self.t("services"))
            if not matches:
                self.ui.line(self.t("no_services"))
            for service in matches[page * 6:page * 6 + 6]:
                self.ui.line(f"#{service['service']}  {service.get('name', '')}", "accent")
                self.ui.line(f"{service.get('platform', '')}  /  {service.get('rate', '—')} {service.get('currency', 'EUR')} / 1,000  /  {service.get('min')}–{service.get('max')}")
                print()
            self.ui.line(self.t("page", page=page + 1, pages=pages, total=len(matches)))
            self.ui.line(self.t("catalog_nav"))
            choice = self.ask("choose")
            if choice in {"0", ""}:
                return None
            if choice == "n":
                page = min(page + 1, pages - 1)
            elif choice == "p":
                page = max(0, page - 1)
            elif choice == "r":
                refresh = True
            elif choice.isdigit():
                service = next((s for s in services if str(s["service"]) == choice), None)
                if service is None:
                    self.ui.line(self.t("not_found"), "warning")
                    self.pause()
                    continue
                self.detail(service)
                self.ui.choice("1", self.t("new_order"), True)
                self.ui.choice("0", self.t("back"))
                if self.ask("choose") == "1":
                    if select:
                        return service
                    self.purchase(service)
            else:
                self.ui.line(self.t("invalid_choice"), "warning")

    def receipt(self, result):
        self.ui.line(self.t("order_accepted"), "success")
        for key, value in (("order_id", result["order"]), ("charge", f"{result['charge']} {result.get('currency', 'EUR')}" if "charge" in result else self.t("unknown")), ("request_key", result["request_key"])):
            self.ui.line(f"{self.t(key)}: {value}")
        self.balance_at = 0

    def purchase(self, service=None):
        from .cli import target_url

        client = self.client()
        if service is None:
            self.ui.heading(self.t("new_order"))
            self.ui.line(self.t("browse_hint"))
            raw = self.ask("service_id")
            if raw == "0":
                return
            if raw == "":
                service = self.browse(select=True)
                if service is None:
                    return
            else:
                sid = self.number(raw)
                service = next((s for s in self.app.store.catalog(client) if str(s["service"]) == str(sid)), None)
                if service is None:
                    raise NexwaError(self.t("not_found"))
        self.detail(service)
        try:
            link = target_url(self.ask("target"))
        except NexwaError:
            raise NexwaError(self.t("invalid_url")) from None
        quantity = self.number(self.ask("quantity"))
        if not int(service["min"]) <= quantity <= int(service["max"]):
            raise NexwaError(self.t("quantity_limits", minimum=service["min"], maximum=service["max"]))
        params = {"service": int(service["service"]), "link": link, "quantity": quantity}
        self.app.preview(client, params)
        self.ui.heading(self.t("review"))
        for label, value in (("service", service.get("name", service["service"])), ("target", params["link"]), ("quantity", params["quantity"])):
            self.ui.line(f"{self.t(label)}: {value}")
        print()
        self.ui.line(self.t("price_note"), "warning")
        if not self.confirm("purchase_confirm"):
            self.ui.line(self.t("canceled"))
            self.pause()
            return
        key = str(uuid.uuid4())
        self.ui.line(f"{self.t('request_key')}: {key}", "accent")
        self.ui.line(self.t("keep_key"))
        with self.app.store.lock(client.key, key):
            result = self.app.submit(client, {"request_key": key, "params": params, "created_at": timestamp()}, announce=False, warn=self.receipt_warning)
        self.receipt(result)
        self.pause()

    def order_status(self):
        raw = self.ask("order_ids")
        if not raw:
            return
        ids = list(dict.fromkeys(str(self.number(part.strip())) for item in raw.split() for part in item.split(",")))
        if len(ids) > 100:
            raise NexwaError(self.t("status_limit"))
        result = self.client().call("status", **{"order" if len(ids) == 1 else "orders": ",".join(ids)})
        self.ui.heading(self.t("delivery"))
        if "status" in result:
            result = {raw: result}
        for oid, data in result.items():
            self.ui.line(f"#{oid}  /  {self.t(data.get('status', 'unknown'))}", "accent")
            if "error" in data:
                self.ui.line(data["error"], "danger")
            else:
                self.ui.line(f"{self.t('charge')}: {data.get('charge', '—')} {data.get('currency', 'EUR')}")
        self.pause()

    def retry(self):
        from .cli import request_key

        client = self.client()
        key = request_key(self.ask("request_key"))
        with self.app.store.lock(client.key, key):
            record = self.app.store.request(client.key, key)
            if record is None:
                raise NexwaError(self.t("missing_request"))
            for label, value in (("service", record["params"]["service"]), ("target", record["params"]["link"]), ("quantity", record["params"]["quantity"])):
                self.ui.line(f"{self.t(label)}: {value}")
            if not record.get("response") and not self.confirm("retry_confirm"):
                return
            self.receipt(self.app.submit(client, record, announce=False, warn=self.receipt_warning))
        self.pause()

    def refill(self):
        client = self.client()
        order = self.number(self.ask("order_id"))
        if self.confirm("refill_confirm"):
            result = client.call("refill", order=order)
            self.ui.line(f"{self.t('refill_sent')}: {result['refill']}", "success")
        self.pause()

    def orders(self):
        client = self.client()
        page = 0
        while True:
            receipts = self.app.store.history(client.key)
            pages = max(1, math.ceil(len(receipts) / 5))
            self.ui.heading(self.t("orders"))
            self.ui.line(self.t("history_note"))
            print()
            if not receipts:
                self.ui.line(self.t("no_orders"))
            for record in receipts[page * 5:page * 5 + 5]:
                response = record.get("response", {})
                self.ui.line(f"#{response.get('order', '—')}  /  {self.t('service')} {record['params']['service']}  /  {record['params']['quantity']}  /  {self.t('accepted' if response else 'unknown')}", "success" if response else "warning")
                self.ui.line(f"{record['created_at']}  /  {record['request_key']}")
            print()
            for key, label in (("1", "status"), ("2", "retry"), ("3", "refill"), ("0", "back")):
                self.ui.choice(key, self.t(label))
            if pages > 1:
                self.ui.line(f"{page + 1}/{pages}   n / p")
            choice = self.ask("choose")
            if choice in {"0", ""}:
                return
            if choice == "1":
                self.order_status()
            elif choice == "2":
                self.retry()
            elif choice == "3":
                self.refill()
            elif choice == "n":
                page = min(page + 1, pages - 1)
            elif choice == "p":
                page = max(0, page - 1)
            else:
                self.ui.line(self.t("invalid_choice"), "warning")

    def wallet(self, website=False):
        self.ui.heading(self.t("wallet"))
        if not website:
            balance = self.client().call("balance")
            self.ui.line(f"{self.t('balance')}: {balance['balance']} {balance.get('currency', 'EUR')}", "success")
            self.balance, self.balance_at = balance, time.monotonic()
        self.ui.line(self.t("website_help"))
        self.ui.line(ACCOUNT_URL, "accent")
        if self.confirm("open_website"):
            webbrowser.open(ACCOUNT_URL)
        self.pause()

    def run(self):
        while True:
            try:
                self.home()
                choice = self.ask("choose")
                if choice == "0":
                    return
                actions = {"1": self.purchase, "2": self.browse, "3": self.orders, "4": self.wallet, "5": lambda: self.wallet(website=True), "6": self.settings, "7": self.login}
                if choice in actions:
                    actions[choice]()
                else:
                    self.ui.line(self.t("invalid_choice"), "warning")
            except (NexwaError, OSError) as exc:
                self.ui.line(f"{self.t('error')}: {self.error_text(exc)}", "danger")
                self.pause()
