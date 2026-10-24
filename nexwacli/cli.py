"""Interactive panel and script-friendly commands."""

import argparse
import getpass
import json
import os
import re
import sys
import uuid
import webbrowser
from urllib.parse import urlsplit

from . import __version__
from .api import ACCOUNT_URL, API_URL, APIError, Client, NexwaError, validate_key
from .storage import Store, timestamp


def clean(value):
    """Keep untrusted catalog text from writing terminal control sequences."""
    return "".join(c if c.isprintable() else " " for c in str(value))


def positive(value):
    if len(str(value)) > 16 or not re.fullmatch(r"[0-9]+", str(value)) or not 1 <= int(value) <= 9007199254740991:
        raise argparse.ArgumentTypeError("expected a positive integer (at most 2^53 - 1)")
    return int(value)


def request_key(value):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value):
        raise NexwaError("Request keys must be 1-120 letters, digits, dots, underscores, colons or hyphens.", "invalid_request_key")
    return value


def target_url(value):
    try:
        url = urlsplit(value)
        valid = url.scheme in {"https", "http"} and url.hostname and not url.username and not url.password
        _ = url.port
    except ValueError:
        valid = False
    if not valid or len(value) > 500 or any(c.isspace() or not c.isprintable() for c in value):
        raise NexwaError("Use a complete HTTP(S) target URL, at most 500 characters, without credentials or spaces.")
    return value


def table(headers, rows):
    if not rows:
        print("No results.")
        return
    rows = [[clean(cell) for cell in row] for row in rows]
    widths = [min(56, max(len(str(h)), *(len(row[i]) for row in rows))) for i, h in enumerate(headers)]

    def line(row):
        return "  ".join((str(c)[:w - 3] + "..." if len(str(c)) > w else str(c)).ljust(w) for c, w in zip(row, widths)).rstrip()

    print(line(headers))
    print(line(["-" * w for w in widths]))
    for row in rows:
        print(line(row))


def output(value, as_json=False):
    if as_json or isinstance(value, list):
        print(json.dumps(value, ensure_ascii=False, indent=2))
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                item = json.dumps(item, ensure_ascii=False)
            print(f"{clean(key)}: {clean('unknown' if item is None else item)}")
    else:
        print(clean(value))


def confirm(message, yes=False):
    if yes:
        return
    if not sys.stdin.isatty():
        raise NexwaError("Confirmation required. Review the request, then add --yes to submit it in a script.")
    print(message + " [y/N] ", file=sys.stderr, end="", flush=True)
    if input().strip().casefold() not in {"y", "yes"}:
        raise NexwaError("Canceled. No request was submitted.")


class Parser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        result = super().parse_args(args, namespace)
        if not hasattr(result, "json"):
            result.json = False
        if not hasattr(result, "timeout"):
            result.timeout = 30
        return result


def parser():
    # Suppressed defaults let --json work before or after subcommands.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="write JSON (errors go to stderr)")
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS, help="network timeout in seconds, 1-300 (default: 30)")
    root = Parser(prog="nexwa", description="NexwaCLI — your Nexwa account, from the terminal.", parents=[common])
    root.add_argument("--version", action="version", version=f"NexwaCLI {__version__}")
    subs = root.add_subparsers(dest="command")
    subs.add_parser("menu", help="open the interactive panel", parents=[common])
    auth = subs.add_parser("auth", help="manage your customer API key", parents=[common]).add_subparsers(dest="auth_command", required=True)
    auth.add_parser("login", help="validate and save a key using a hidden prompt", parents=[common])
    auth.add_parser("status", help="show local authentication configuration", parents=[common])
    auth.add_parser("logout", help="delete the saved key", parents=[common])
    subs.add_parser("balance", help="fetch the current Nexwa wallet balance", parents=[common])
    services = subs.add_parser("services", help="browse the Nexwa catalog", parents=[common])
    services.add_argument("service", nargs="?", type=positive, help="show a single service with its description")
    services.add_argument("--search", default="", help="search name, category, platform and description")
    services.add_argument("--platform", default="", help="filter by platform (case insensitive)")
    services.add_argument("--category", default="", help="filter by category text")
    services.add_argument("--limit", type=positive, default=50, help="maximum results (default: 50)")
    services.add_argument("--all", action="store_true", help="return all matching services")
    services.add_argument("--refresh", action="store_true", help="ignore the 12-hour local catalog cache")
    orders = subs.add_parser("orders", help="place and track orders", parents=[common]).add_subparsers(dest="order_command", required=True)
    create = orders.add_parser("create", help="place an order using your Nexwa credit", parents=[common])
    create.add_argument("--service", type=positive, required=True)
    create.add_argument("--link", required=True)
    create.add_argument("--quantity", type=positive, required=True)
    create.add_argument("--request-key", help="stable idempotency key for this purchase (generated if omitted)")
    create.add_argument("--dry-run", action="store_true", help="validate and preview without submitting an order")
    create.add_argument("--yes", "-y", action="store_true", help="confirm spending Nexwa wallet credit")
    status = orders.add_parser("status", help="check up to 100 API order IDs", parents=[common])
    status.add_argument("ids", nargs="+", help="numeric IDs separated by spaces or commas")
    listing = orders.add_parser("list", help="show orders recorded on this computer for this key", parents=[common])
    listing.add_argument("--pending", action="store_true", help="only requests without a saved success response")
    retry = orders.add_parser("retry", help="resubmit a saved purchase with the same idempotency key", parents=[common])
    retry.add_argument("request_key")
    retry.add_argument("--yes", "-y", action="store_true")
    refill = orders.add_parser("refill", help="request a refill for an eligible order", parents=[common])
    refill.add_argument("order", type=positive)
    refill.add_argument("--yes", "-y", action="store_true")
    account = subs.add_parser("account", help="find wallet funding and API key settings on the website", parents=[common])
    account.add_argument("--open", action="store_true", help="open your account in the default browser")
    settings = subs.add_parser("settings", help="view or change panel language and colors", parents=[common])
    settings.add_argument("--language", choices=["en", "it", "fr", "de", "es", "ru"])
    settings.add_argument("--color", choices=["auto", "on", "off"])
    return root


class App:
    def __init__(self, store=None, client_factory=Client):
        self.store = store if store is not None else Store()
        self.client_factory = client_factory

    def key(self):
        key = os.environ.get("NEXWA_API_KEY") or self.store.saved_key()
        if not key:
            raise NexwaError("No API key configured. Run 'nexwa auth login' or set NEXWA_API_KEY.")
        return validate_key(key)

    def client(self, args):
        return self.client_factory(self.key(), timeout=args.timeout)

    def login(self, args):
        if not sys.stdin.isatty():
            raise NexwaError("Login needs an interactive terminal. Set NEXWA_API_KEY when running scripts.")
        print("Generate a customer key in Nexwa > Wallet and API > API keys.", file=sys.stderr)
        print("The key will be saved unencrypted on this computer. Use NEXWA_API_KEY for session-only access.", file=sys.stderr)
        key = validate_key(getpass.getpass("Customer API key (hidden): "))
        balance = self.client_factory(key, timeout=args.timeout).call("balance")
        self.store.save_key(key)
        result = {"authenticated": True, "balance": balance["balance"], "currency": balance.get("currency", "EUR"), "config": str(self.store.config_path)}
        if os.environ.get("NEXWA_API_KEY"):
            result["note"] = "NEXWA_API_KEY is set and takes precedence over the key just saved."
        return result

    def services(self, args, client):
        services = self.store.catalog(client, refresh=args.refresh)
        if args.service:
            match = next((s for s in services if str(s["service"]) == str(args.service)), None)
            if match is None:
                raise NexwaError("Service not found. Refresh the catalog with --refresh.")
            return match
        matches = [s for s in services if
                   (not args.platform or str(s.get("platform", "")).casefold() == args.platform.casefold()) and
                   args.category.casefold() in str(s.get("category", "")).casefold() and
                   args.search.casefold() in " ".join(str(s.get(k, "")) for k in ("name", "platform", "category", "description")).casefold()]
        return matches if args.all else matches[:args.limit]

    def preview(self, client, params):
        service = next((s for s in self.store.catalog(client) if str(s["service"]) == str(params["service"])), None)
        if service is None:
            raise NexwaError("Service not found. Run 'nexwa services --refresh' and check its ID.", "not_found")
        try:
            minimum, maximum = int(service["min"]), int(service["max"])
        except (KeyError, TypeError, ValueError):
            raise NexwaError("The catalog has invalid quantity limits. Refresh it before ordering.", "invalid_response") from None
        if not minimum <= params["quantity"] <= maximum:
            raise NexwaError(f"This service accepts quantities between {minimum} and {maximum}.", "quantity_limits", minimum=minimum, maximum=maximum)
        return {
            "service": params["service"], "name": service.get("name", ""),
            "link": params["link"], "quantity": params["quantity"],
            "min": minimum, "max": maximum,
            "rate_per_1000": service.get("rate"),
            "price_per_item": service.get("price_per_item"),
            "pricing_unit": service.get("pricing_unit"),
            "currency": service.get("currency", "EUR"),
            "pricing_note": "Catalog prices are references. Nexwa calculates the final charge when accepting the order, including applicable minimums and promotions.",
        }

    def submit(self, client, record, announce=True, warn=None):
        key = record["request_key"]
        if record.get("response"):
            return {**record["response"], "request_key": key, "local_replay": True}
        # This write must succeed BEFORE any request capable of spending credit.
        record["state"] = "pending"
        record["updated_at"] = timestamp()
        self.store.save_request(client.key, record)
        if announce:
            print(f"Request key: {key}. Keep it if the connection is interrupted.", file=sys.stderr)
        response = client.call("add", **record["params"], idempotency_key=key)
        record["response"] = response
        record["state"] = "accepted"
        record["updated_at"] = timestamp()
        try:
            self.store.save_request(client.key, record)
        except OSError:
            if warn:
                warn()
            else:
                print("Order accepted, but the local receipt could not be saved. Keep the response and request key.", file=sys.stderr)
        return {**response, "request_key": key}

    def create(self, args, client):
        params = {"service": args.service, "link": target_url(args.link), "quantity": args.quantity}
        key = request_key(args.request_key or str(uuid.uuid4()))
        with self.store.lock(client.key, key):
            existing = self.store.request(client.key, key)
            if existing and existing.get("params") != params:
                raise NexwaError("This request key already belongs to a different purchase. Use a new key for a new order.")
            if existing:
                if args.dry_run:
                    return {"dry_run": True, "request_key": key, "saved_request": existing}
                if existing.get("response"):
                    return self.submit(client, existing)
                confirm("Retry this saved purchase using Nexwa wallet credit?", args.yes)
                return self.submit(client, existing)
            preview = self.preview(client, params)
            if args.dry_run:
                return {"dry_run": True, **preview}
            if not args.json:
                output(preview)
            confirm("Submit this order and authorize the charge calculated by Nexwa?", args.yes)
            return self.submit(client, {"request_key": key, "params": params, "created_at": timestamp()})

    def retry(self, args, client):
        key = request_key(args.request_key)
        with self.store.lock(client.key, key):
            record = self.store.request(client.key, key)
            if record is None:
                raise NexwaError("No saved request with this key for the active API key on this computer.")
            if not record.get("response"):
                if not args.json:
                    output(record["params"])
                confirm("Retry this purchase using its original request key and Nexwa wallet credit?", args.yes)
            return self.submit(client, record)

    def run(self, args):
        if args.command == "settings":
            changes = {k: getattr(args, k) for k in ("language", "color") if getattr(args, k) is not None}
            if changes:
                self.store.save_settings(**changes)
            return {"language": "en", "color": "auto", **self.store.settings()}
        if args.command == "auth":
            if args.auth_command == "login":
                return self.login(args)
            if args.auth_command == "logout":
                self.store.logout()
                return {"saved_key_removed": True, "environment_key_active": bool(os.environ.get("NEXWA_API_KEY"))}
            key = os.environ.get("NEXWA_API_KEY") or self.store.saved_key()
            return {"configured": bool(key), "source": "environment" if os.environ.get("NEXWA_API_KEY") else "file" if key else "none", "config": str(self.store.config_path), "endpoint": API_URL}
        if args.command == "account":
            if args.open and not webbrowser.open(ACCOUNT_URL):
                raise NexwaError(f"Could not open a browser. Visit {ACCOUNT_URL}")
            return {"account": ACCOUNT_URL, "note": "Fund your Nexwa wallet, verify your email and manage customer API keys on the website."}
        if args.command == "orders" and args.order_command == "list":
            records = self.store.history(self.key())
            return [r for r in records if not args.pending or not r.get("response")]
        client = self.client(args)
        if args.command == "balance":
            return client.call("balance")
        if args.command == "services":
            return self.services(args, client)
        if args.command == "orders":
            if args.order_command == "create":
                return self.create(args, client)
            if args.order_command == "retry":
                return self.retry(args, client)
            if args.order_command == "refill":
                confirm(f"Request a refill for order {args.order}? Eligibility is checked by Nexwa.", args.yes)
                return client.call("refill", order=args.order)
            if args.order_command == "status":
                try:
                    ids = list(dict.fromkeys(str(positive(part.strip())) for item in args.ids for part in item.split(",")))
                except argparse.ArgumentTypeError as exc:
                    raise NexwaError(str(exc)) from None
                if len(ids) > 100:
                    raise NexwaError("Request at most 100 distinct order IDs at a time.")
                return client.call("status", **{"order" if len(ids) == 1 else "orders": ",".join(ids)})
        raise NexwaError("Choose a command. Run 'nexwa --help' for usage.")

    def display(self, args, result):
        if args.json:
            output(result, True)
        elif args.command == "services" and isinstance(result, list):
            table(["ID", "Platform", "Service", "EUR / 1k", "Min", "Max", "Refill"], [
                [s["service"], s.get("platform", ""), s.get("name", ""), s.get("rate", ""), s.get("min", ""), s.get("max", ""), "yes" if s.get("refill") else "no"] for s in result])
            print("Catalog reference prices. Use 'nexwa services <ID>' for pricing units and details.")
            print("Showing up to the selected limit. Use --all for all matches, --refresh for current data.")
        elif args.command == "orders" and args.order_command == "list":
            table(["Created (UTC)", "Order", "Service", "Qty", "Local state", "Request key"], [
                [r["created_at"], r.get("response", {}).get("order", "unknown"), r["params"]["service"], r["params"]["quantity"], r.get("state", "pending"), r["request_key"]] for r in result])
            print("Local receipts for this API key. Use 'orders status <ID>' for live delivery status.")
        else:
            output(result)

    def menu(self):
        from .panel import Panel

        Panel(self).run()


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    app = App()
    try:
        if args.command in {None, "menu"}:
            if not sys.stdin.isatty() or args.json:
                if args.command == "menu" or args.json:
                    raise NexwaError("The menu requires an interactive terminal without --json.")
                root.print_help()
                return 0
            app.menu()
        else:
            app.display(args, app.run(args))
        return 0
    except (KeyboardInterrupt, EOFError):
        print("\nStopped. Keep the original request key for any interrupted purchase.", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0
    except (NexwaError, OSError) as exc:
        if args.json:
            error = {"error": str(exc)}
            if isinstance(exc, APIError):
                error.update(http_status=exc.status, retry_after=exc.retry_after)
            print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"Error: {clean(exc)}", file=sys.stderr)
        return 1
