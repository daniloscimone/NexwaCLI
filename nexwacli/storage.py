"""Private local configuration, catalog cache, and per-request order journal."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from .api import API_URL, NexwaError

CACHE_SECONDS = 12 * 60 * 60


def data_directory():
    if os.environ.get("NEXWA_CONFIG_DIR"):
        return Path(os.environ["NEXWA_CONFIG_DIR"]).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "NexwaCLI"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "nexwa"


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path, default=None):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except (ValueError, UnicodeError):
        raise NexwaError(f"Invalid local JSON file: {path}. Restore or move it before continuing.", "local_file_error", path=path) from None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkstemp creates mode 0600; replace keeps readers from seeing partial JSON.
    fd, name = tempfile.mkstemp(prefix=".nexwa-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else data_directory()

    @property
    def config_path(self):
        return self.root / "config.json"

    def saved_key(self):
        config = read_json(self.config_path, {})
        if not isinstance(config, dict) or not isinstance(config.get("api_key", ""), str):
            raise NexwaError(f"Invalid configuration: {self.config_path}.", "local_file_error", path=self.config_path)
        return config.get("api_key", "")

    def save_key(self, key):
        write_json(self.config_path, {"api_key": key})

    def settings(self):
        value = read_json(self.root / "settings.json", {})
        if not isinstance(value, dict):
            raise NexwaError("Invalid local settings file.", "local_file_error", path=self.root / "settings.json")
        return value

    def save_settings(self, **changes):
        write_json(self.root / "settings.json", {**self.settings(), **changes})

    def logout(self):
        self.config_path.unlink(missing_ok=True)

    def scope(self, key):
        # Isolate history and cache when the active customer key changes.
        digest = hashlib.sha256((API_URL + "\0" + key).encode()).hexdigest()[:24]
        return self.root / "accounts" / digest

    def catalog(self, client, refresh=False):
        path = self.scope(client.key) / "services.json"
        cached = read_json(path)
        if not refresh and isinstance(cached, dict):
            saved = cached.get("saved_at")
            services = cached.get("services")
            if isinstance(saved, (float, int)) and 0 <= time.time() - saved < CACHE_SECONDS and isinstance(services, list):
                return services
        services = client.call("services")
        write_json(path, {"saved_at": time.time(), "services": services})
        return services

    def request_path(self, key, request_key):
        digest = hashlib.sha256(request_key.encode()).hexdigest()
        return self.scope(key) / "orders" / f"{digest}.json"

    def request(self, key, request_key):
        record = read_json(self.request_path(key, request_key))
        if record is not None and (not isinstance(record, dict) or record.get("request_key") != request_key):
            raise NexwaError("Invalid order journal entry. Restore it before retrying.", "local_file_error", path=self.request_path(key, request_key))
        return record

    def save_request(self, key, record):
        write_json(self.request_path(key, record["request_key"]), record)

    def history(self, key):
        directory = self.scope(key) / "orders"
        records = [read_json(path) for path in directory.glob("*.json")]
        if any(not isinstance(r, dict) or "created_at" not in r for r in records):
            raise NexwaError("Invalid local order history.", "local_file_error", path=directory)
        return sorted(records, key=lambda r: r["created_at"], reverse=True)

    @contextmanager
    def lock(self, key, request_key):
        path = self.request_path(key, request_key).with_suffix(".lock")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise NexwaError(
                f"This request is locked: {path}. If a previous process crashed, "
                "first make sure no NexwaCLI process is using it, then remove this .lock file.",
                "locked_request", path=path,
            ) from None
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            yield
        finally:
            path.unlink(missing_ok=True)
