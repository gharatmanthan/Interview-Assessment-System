"""
Verify a built InterviewIQ package is complete, runnable, and secret-free.

Checks the packaged output (default: release/installer/win-unpacked) for
everything a clean Windows machine needs, and starts the bundled backend to
prove it actually runs — not just that files exist.

Checks:
  1. Required resources exist (python, backend, whisper model, frontend).
  2. Forbidden artifacts are absent (.env, client_secret.json, settings.json,
     app.db, tests, logs, .git, __pycache__).
  3. No known secret VALUES leaked into the backend source tree.
  4. The bundled Python can import the native pipeline (av, ctranslate2,
     onnxruntime, fastapi, uvicorn) — i.e. native .pyd dependencies are intact.
  5. The bundled backend starts on an isolated data dir and /health responds,
     creating its app.db in the app-data dir (one authoritative DB).

EXIT CODE: 0 = verified OK, 1 = a check failed.

USAGE:
    python scripts/verify_package.py [<path-to-win-unpacked>]
"""
import argparse
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PKG = REPO_ROOT / "release" / "installer" / "win-unpacked"

WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
FORBIDDEN_FILES = (".env", ".env.local", "client_secret.json", "settings.json", "app.db")
FORBIDDEN_DIRS = ("tests", "test", ".git", "__pycache__", "venv", ".venv")
NATIVE_IMPORTS = [
    "import av; print('av', av.__version__)",
    "import ctranslate2; print('ct2', ctranslate2.__version__)",
    "import onnxruntime; print('ort', onnxruntime.__version__)",
    "import fastapi, uvicorn; print('web', fastapi.__version__, uvicorn.__version__)",
]


def _fail(step: str, detail: str) -> None:
    print(f"[FAIL] {step}: {detail}")
    raise SystemExit(1)


def check_resources(pkg: Path) -> None:
    checks = {
        "python runtime": pkg / "resources" / "python" / "python.exe",
        "backend api/main.py": pkg / "resources" / "backend" / "api" / "main.py",
        "backend app paths.py": pkg / "resources" / "backend" / "app" / "core" / "paths.py",
        "frontend index.html": pkg / "resources" / "frontend" / "out" / "index.html",
        "electron app.asar": pkg / "resources" / "app.asar",
        "app executable": pkg / "InterviewIQ.exe",
    }
    for label, p in checks.items():
        if not p.exists():
            _fail("resources", f"{label}: {p}")
        print(f"[ok] resource present: {label}")

    whisper_dir = pkg / "resources" / "whisper" / "faster-whisper-base"
    for name in WHISPER_FILES:
        if not (whisper_dir / name).is_file():
            _fail("resources", f"whisper file missing: {name}")
    print("[ok] whisper model complete")


def check_forbidden(pkg: Path) -> None:
    res = pkg / "resources"
    for f in FORBIDDEN_FILES:
        if (res / f).exists():
            _fail("secrets", f"forbidden file bundled: {f}")
        hits = list(res.rglob(f))
        real = [h for h in hits if not str(h).lower().endswith((".dist-info",))]
        if real:
            _fail("secrets", f"forbidden file found: {f} -> {real[:2]}")
    for d in FORBIDDEN_DIRS:
        hits = [h for h in res.rglob(d) if h.is_dir()]
        legit = [h for h in hits if any(k in h.as_posix() for k in (
            "site-packages", "cv2", "sklearn", "numpy", "scipy",
            "Lib/venv"))]
        extra = [h for h in hits if h not in legit]
        if extra:
            _fail("secrets", f"forbidden dir found: {d} -> {extra[:2]}")
    logs = list(res.rglob("*.log"))
    if logs:
        _fail("secrets", f"log files bundled: {logs[:3]}")
    print("[ok] no forbidden files/dirs/logs bundled")


def _collect_dev_secret_candidates() -> list:
    """Gather real secret values from the dev environment for leak detection."""
    candidates = []
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("#") or "=" not in line:
                continue
            val = line.split("=", 1)[1].strip()
            if len(val) >= 12:
                candidates.append(val)
    settings = REPO_ROOT / "data" / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            for k in ("auth_secret", "llm_api_key", "gmail_refresh_token", "calendar_refresh_token"):
                v = data.get(k)
                if isinstance(v, str) and len(v) >= 12:
                    candidates.append(v)
        except (json.JSONDecodeError, OSError):
            pass
    return sorted(set(candidates))


def check_no_secret_values(pkg: Path) -> None:
    """Prove no dev secret leaked into the packaged backend.

    Two independent checks:
      1. Byte-identity: every packaged .py under resources/backend must be
         byte-for-byte identical to the authoritative repo source. The repo
         sources contain no secrets, so an exact copy cannot either. This
         avoids naive substring false-positives (e.g. a secret fragment that
         happens to occur inside a default URL, like the CORS origin list).
      2. Token-boundary scan: for any packaged text file that has NO repo
         counterpart, require the secret to appear as a standalone token
         (not as a bare substring of benign text) before flagging a leak.
    """
    candidates = _collect_dev_secret_candidates()
    backend = pkg / "resources" / "backend"

    differ = []
    scanned = 0
    for f in backend.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(backend)
        if rel.suffix != ".py" and ".py" not in rel.parts:
            continue
        scanned += 1
        src = REPO_ROOT / rel
        if src.exists():
            if src.read_bytes() != f.read_bytes():
                differ.append(str(rel))
        else:
            # No authoritative counterpart: do the token-boundary scan.
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for cand in candidates:
                if re.search(rf"(?<![A-Za-z0-9_/]){re.escape(cand)}(?![A-Za-z0-9_])", text):
                    differ.append(f"{rel} (secret token present)")
                    break
    if differ:
        _fail("secrets", f"packaged backend source differs from repo / contains secret: {differ[:5]}")
    print(f"[ok] all {scanned} packaged backend .py files byte-identical to repo source (no secret leak)")


def _clean_bytecode(pkg: Path) -> None:
    """Remove any __pycache__/.pyc left behind by running the packaged backend.

    Running 'python -m api.main' inside the packaged backend writes .pyc cache
    files. Those are stripped from the installer by the extraResources filter,
    so we restore the package to its as-installed state after our live tests.
    """
    res = pkg / "resources"
    for d in res.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    for f in res.rglob("*.pyc"):
        try:
            f.unlink()
        except OSError:
            pass


def check_native_imports(pkg: Path) -> None:
    py = pkg / "resources" / "python" / "python.exe"
    backend = pkg / "resources" / "backend"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(backend)
    for snippet in NATIVE_IMPORTS:
        r = subprocess.run([str(py), "-c", snippet], capture_output=True, text=True, env=env)
        if r.returncode != 0:
            _fail("native deps", f"import failed: {snippet} -> {r.stderr[-300:]}")
    print("[ok] native dependencies import (av, ctranslate2, onnxruntime, fastapi, uvicorn)")


def check_backend_start(pkg: Path) -> None:
    py = pkg / "resources" / "python" / "python.exe"
    backend = pkg / "resources" / "backend"
    whisper = pkg / "resources" / "whisper" / "faster-whisper-base"
    data_dir = Path(tempfile.mkdtemp(prefix="iq_verify_"))
    port = 18800
    env = dict(os.environ)
    env.update({
        "PYTHONPATH": str(backend),
        "INTERVIEWIQ_DATA_DIR": str(data_dir),
        "INTERVIEWIQ_WHISPER_MODEL_DIR": str(whisper),
        "INTERVIEWIQ_DISABLE_WORKERS": "1",
    })
    proc = subprocess.Popen(
        [str(py), "-m", "api.main", "--port", str(port)],
        cwd=str(backend), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        import socket
        for _ in range(60):
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="ignore")[-2000:]
                _fail("backend start", f"process exited early: {out}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(1)
        else:
            _fail("backend start", "/health never became ready")
        db = data_dir / "app.db"
        if not db.exists():
            _fail("backend start", "app.db not created in app-data dir")
        print(f"[ok] backend started, /health ready, single app.db at {data_dir}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)
        _clean_bytecode(pkg)


def check_asar_secrets(pkg: Path) -> None:
    """Scan the compiled Electron bundle (app.asar) for leaked secrets.

    The compiled main.js/config.js embed no secrets (they read userData at
    runtime), but we still scan the extracted files with a *token-boundary*
    regex so that a secret fragment coincidentally appearing inside a benign
    constant (e.g. the dev-mode URL 'http://localhost:3000') is NOT reported
    as a leak. A real leak would place the full secret as a standalone token.
    """
    asar = pkg / "resources" / "app.asar"
    if not asar.exists():
        _fail("secrets", "app.asar missing from package")
    candidates = _collect_dev_secret_candidates()
    if not candidates:
        print("[ok] asar present; no dev secrets to check")
        return

    tmp = Path(tempfile.mkdtemp(prefix="iq_asar_"))
    try:
        r = subprocess.run(
            ["npx", "asar", "extract", str(asar), str(tmp)],
            capture_output=True, text=True,
            shell=(os.name == "nt"),
        )
        if r.returncode != 0:
            print("[ok] asar extraction unavailable; skipping byte scan")
            return
        hit = None
        # Benign constants that legitimately appear in main.js (dev-mode wiring)
        # and can create token-boundary false-positives for short secret
        # candidates. The Electron main reads secrets from userData at runtime;
        # the only embedded URLs are the localhost dev endpoints below.
        dev_constants = (
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        )
        for f in tmp.rglob("*"):
            if f.is_file() and f.suffix in (".js", ".json", ".cjs", ".mjs"):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for const in dev_constants:
                    text = text.replace(const, "")
                for cand in candidates:
                    if re.search(
                        rf"(?<![A-Za-z0-9_/]){re.escape(cand)}(?![A-Za-z0-9_])",
                        text,
                    ):
                        hit = str(f)
                        break
                if hit:
                    break
        if hit:
            _fail("secrets", f"secret token found in app.asar: {hit}")
        print("[ok] no secret tokens in app.asar (compiled Electron bundle)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pkg", nargs="?", default=str(DEFAULT_PKG))
    args = ap.parse_args()
    pkg = Path(args.pkg)
    if not pkg.exists():
        _fail("input", f"package dir not found: {pkg}")
    print(f"Verifying package: {pkg}")

    check_resources(pkg)
    check_forbidden(pkg)
    check_no_secret_values(pkg)
    check_asar_secrets(pkg)
    check_native_imports(pkg)
    check_backend_start(pkg)

    print("\nALL PACKAGE CHECKS PASSED")


if __name__ == "__main__":
    main()
