"""Resolve a pinned, checksum-verified binary for a wrapper script (scripts/gitleaks, scripts/vale).

Resolution order, the same for every tool:
  1. <PREFIX>_BIN: an operator-installed binary. Its version output must equal the pinned
     one exactly, unless the tool names an allow-unpinned variable and it is set to 1. A
     binary whose SHA-256 differs from the pinned release build runs with a notice, since a
     package-manager build differs legitimately.
  2. A verified copy under ${XDG_CACHE_HOME:-$HOME/.cache}/vault-kit/<name>-<version>/,
     re-hashed on every run. The cache directories must be yours and not writable by others.
  3. A download of the pinned release archive, verified before it is parsed; the binary is
     read from it in memory and verified again before it is written.

Every failure raises Refusal. Its kind is "unavailable" (no build for this platform, the
download failed) or "integrity" (anything that could mean tampering); each wrapper maps the
kinds to exit codes. Nothing unverified is ever returned without the operator asking for it.
"""
import vaultconf  # noqa: F401  (toolchain preflight)
from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

UNAVAILABLE, INTEGRITY = "unavailable", "integrity"
DOWNLOAD_SCHEMES = ("https://", "http://", "file://")
INTEGRITY_NOTE = "Refusing to run it. Do not retry; report it."


class Refusal(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class ToolSpec:
    name: str                 # binary name, archive member, and cache directory prefix
    version: str
    release_url: str          # directory holding the archives
    archives: dict            # platform key (darwin_arm64, ...) -> archive file name
    pins: dict                # platform key -> {"archive": sha256, "binary": sha256}
    env_prefix: str           # GITLEAKS -> GITLEAKS_BIN, GITLEAKS_DOWNLOAD_BASE
    version_args: tuple       # argv after the binary that prints its version
    version_output: str       # that command's exact stdout, stripped
    install_hint: str
    allow_unpinned_env: str | None = None  # set to 1 to run a *_BIN of another version, with a warning
    closed_note: str = ""     # appended to a version refusal (the secret scan fails closed)

    def env(self, suffix):
        return os.environ.get(f"{self.env_prefix}_{suffix}")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def platform_key():
    machine = platform.machine().lower()
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(machine)
    return f"{platform.system().lower()}_{arch}"


def target(spec):
    key = platform_key()
    if key not in spec.pins:
        raise Refusal(UNAVAILABLE, f"no pinned {spec.name} build for {platform.system()} "
                                   f"{platform.machine().lower()}. {spec.install_hint}")
    return key


def fetch(spec, url):
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()
    except Exception as error:  # noqa: BLE001  (any failure falls through to curl)
        first = error
    curl = shutil.which("curl")
    if curl:
        # --url: a value that starts with "-" stays a URL, never a curl option.
        result = subprocess.run([curl, "-fsSL", "--max-time", "120", "--url", url], capture_output=True)
        if result.returncode == 0:
            return result.stdout
    raise Refusal(UNAVAILABLE, f"could not download {url} ({first}). {spec.install_hint}")


def make_private_dirs(directory):
    """Create each missing level of directory as 0700, whatever the umask (mkdir's mode is masked
    by it, so a umask of 002 would leave group-writable directories behind)."""
    missing = []
    for level in [directory, *directory.parents]:
        if level.exists() or level.is_symlink():
            break
        missing.append(level)
    for level in reversed(missing):
        level.mkdir(mode=0o700)
        os.chmod(level, 0o700)


def refuse_shared(path, kind="directory"):
    """A cache path someone else can write could swap the binary between hash and exec."""
    info = path.lstat()
    plain = stat.S_ISDIR(info.st_mode) if kind == "directory" else stat.S_ISREG(info.st_mode)
    if stat.S_ISLNK(info.st_mode) or not plain:
        raise Refusal(INTEGRITY, f"cache path {path} is not a plain {kind}. {INTEGRITY_NOTE}")
    if info.st_uid != os.getuid():
        raise Refusal(INTEGRITY, f"cache {kind} {path} is not owned by you. {INTEGRITY_NOTE}")
    if info.st_mode & 0o022:
        raise Refusal(INTEGRITY, f"cache {kind} {path} is writable by others, so another user could "
                                 f"swap the binary. Run `chmod go-w {path}` if you made it, then retry.")


def download(spec, key, binary):
    pins, archive_name = spec.pins[key], spec.archives[key]
    base = spec.env("DOWNLOAD_BASE") or spec.release_url
    if not base.startswith(DOWNLOAD_SCHEMES):
        raise Refusal(INTEGRITY, f"{spec.env_prefix}_DOWNLOAD_BASE must start with "
                                 f"{', '.join(DOWNLOAD_SCHEMES)}; got {base!r}")
    print(f"{spec.name} wrapper: downloading {spec.name} {spec.version} to {binary.parent}",
          file=sys.stderr)
    archive = fetch(spec, f"{base.rstrip('/')}/{archive_name}")
    if sha256(archive) != pins["archive"]:
        raise Refusal(INTEGRITY, f"checksum mismatch for downloaded {archive_name}: expected "
                                 f"{pins['archive']}, got {sha256(archive)}. {INTEGRITY_NOTE}")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        try:
            member = tar.getmember(spec.name)
        except KeyError:
            raise Refusal(INTEGRITY, f"{archive_name} has no {spec.name} member. {INTEGRITY_NOTE}") from None
        if not member.isfile():
            raise Refusal(INTEGRITY, f"{archive_name}: {spec.name} is not a regular file. {INTEGRITY_NOTE}")
        data = tar.extractfile(member).read()
    if sha256(data) != pins["binary"]:
        raise Refusal(INTEGRITY, f"checksum mismatch for {spec.name} inside {archive_name}: expected "
                                 f"{pins['binary']}, got {sha256(data)}. {INTEGRITY_NOTE}")
    # Write beside the target and rename, so a concurrent run never sees a partial file.
    with tempfile.NamedTemporaryFile(dir=binary.parent, delete=False) as temp:
        temp.write(data)
    os.chmod(temp.name, 0o755)
    os.replace(temp.name, binary)


def resolve_override(spec, override):
    variable = f"{spec.env_prefix}_BIN"
    if not (os.path.isfile(override) and os.access(override, os.X_OK)):
        raise Refusal(INTEGRITY, f"{variable}={override} is not an executable file. {spec.install_hint}")
    try:
        found = subprocess.run([override, *spec.version_args], capture_output=True, text=True,
                               timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        found = ""
    allow = spec.allow_unpinned_env
    if found != spec.version_output:
        if not allow or os.environ.get(allow) != "1":
            fix = (f"Install {spec.name} {spec.version}, or set {allow}=1 to run it anyway."
                   if allow else f"Install {spec.name} {spec.version}.")
            raise Refusal(INTEGRITY, " ".join(filter(None, [
                f"{variable}={override} reports version {found or '(none)'}, not the pinned "
                f"{spec.version}.", fix, spec.closed_note])))
        print(f"{spec.name} wrapper: WARNING: {allow}=1: running {variable}={override}, which reports "
              f"version {found or '(none)'}, not the pinned {spec.version}. Its result is not the "
              "pinned scan's result.", file=sys.stderr)
        return override
    pin = spec.pins.get(platform_key())
    if pin and sha256(Path(override).read_bytes()) != pin["binary"]:
        print(f"{spec.name} wrapper: note: {variable}={override} reports {spec.version} but is not "
              "hash-verified (it differs from the pinned release build).", file=sys.stderr)
    return override


def resolve(spec):
    override = spec.env("BIN")
    if override:
        return resolve_override(spec, override)
    key = target(spec)
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "vault-kit"
    binary = cache / f"{spec.name}-{spec.version}" / spec.name
    make_private_dirs(binary.parent)
    refuse_shared(cache)
    refuse_shared(binary.parent)
    if not binary.is_file():
        download(spec, key, binary)
    refuse_shared(binary, kind="file")
    found = sha256(binary.read_bytes())
    if found != spec.pins[key]["binary"]:
        raise Refusal(INTEGRITY, f"checksum mismatch for cached {binary}: expected "
                                 f"{spec.pins[key]['binary']}, got {found}. Refusing to run it. "
                                 f"Delete {binary.parent} to download a fresh copy.")
    return str(binary)


def main(spec, argv, unavailable_exit):
    """Resolve, then print the path (--vault-resolve) or exec the binary with argv."""
    try:
        path = resolve(spec)
    except Refusal as refusal:
        print(f"{spec.name} wrapper: {refusal}", file=sys.stderr)
        raise SystemExit(unavailable_exit if refusal.kind == UNAVAILABLE else 2)
    except Exception as error:  # noqa: BLE001  exit 2, never 1: callers read 1 as findings
        print(f"{spec.name} wrapper: could not resolve {spec.name} ({type(error).__name__}: {error}). "
              f"Nothing was run.", file=sys.stderr)
        raise SystemExit(2)
    if argv == ["--vault-resolve"]:
        print(path)
        raise SystemExit(0)
    os.execv(path, [path, *argv])
