"""Smoke-test a built executable, then create its distributable archive."""

import hashlib
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nexwacli import __version__


def main():
    target = os.environ["NEXWA_BUILD_TARGET"]
    architecture = platform.machine().lower()
    expected = {"x64": {"x86_64", "amd64"}, "arm64": {"arm64", "aarch64"}}
    if architecture not in expected[target.rsplit("-", 1)[1]]:
        raise RuntimeError(f"Target {target} does not match build architecture {architecture}.")
    executable = Path("dist") / ("nexwa.exe" if target.startswith("windows") else "nexwa")
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, "NEXWA_CONFIG_DIR": directory}
        env.pop("NEXWA_API_KEY", None)
        version = subprocess.check_output([str(executable.resolve()), "--version"], env=env, text=True).strip()
        assert version == f"NexwaCLI {__version__}", version
        subprocess.run([str(executable.resolve()), "--help"], env=env, check=True)
        subprocess.run([str(executable.resolve()), "settings", "--language", "it", "--json"], env=env, check=True)
        subprocess.run([str(executable.resolve()), "auth", "status", "--json"], env=env, check=True)
    output = Path("packages")
    output.mkdir(exist_ok=True)
    base = f"nexwa-{__version__}-{target}"
    files = [(executable, executable.name), (Path("README.md"), "README.md"), (Path("LICENSE"), "LICENSE")]
    if target.startswith("windows"):
        archive = output / f"{base}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for path, name in files:
                handle.write(path, f"{base}/{name}")
    else:
        archive = output / f"{base}.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            for path, name in files:
                handle.add(path, arcname=f"{base}/{name}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"Packaged {archive}")


if __name__ == "__main__":
    main()
