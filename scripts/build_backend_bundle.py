"""
Build the self-contained InterviewIQ backend bundle for Electron packaging.

Assembles everything a clean, non-technical Windows machine needs to run the
InterviewIQ desktop app WITHOUT Python, pip, a venv, system FFmpeg, or a
manual Whisper model download:

    release/portable/
      python/                     # portable CPython (python.exe + stdlib + DLLs)
        Lib/site-packages/        # all runtime Python dependencies (+ native .pyd)
      backend/
        api/                      # FastAPI application source
        app/                      # shared application source
      whisper/
        faster-whisper-base/      # bundled Whisper "base" model (config/model/tokenizer/vocab)
      frontend/
        out/                      # static Next.js export served by Electron

The bundle is produced from LOCAL artifacts only:
  * the active Python environment that already has all deps installed
    (python.exe itself + Lib/site-packages),
  * the repository api/ and app/ source trees,
  * the Whisper "base" model already present in the HuggingFace cache.

Secrets (data/settings.json, client_secret.json, .env) and user data are
NEVER copied. They live in the per-user app-data dir at runtime instead.

USAGE (from repo root, with the project venv active):
    python scripts/build_backend_bundle.py
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTABLE_ROOT = REPO_ROOT / "release" / "portable"


def _log(msg: str) -> None:
    print(f"[build_backend_bundle] {msg}")


def _is_test_artifact(rel: str, item: Path) -> bool:
    """True for third-party test dirs/files that are never needed at runtime."""
    parts = {p.lower() for p in rel.split("/")}
    if parts & {"tests", "test", "testing"}:
        return True
    if item.is_file():
        name = item.name.lower()
        return name.startswith("test_") or name.endswith("_test.py") or name.endswith("tests.py")
    return False


def _copy_tree(src: Path, dst: Path, exclude_prefixes: tuple[str, ...] = (),
               drop_tests: bool = False) -> None:
    """Copy src -> dst, skipping any entry whose relpath starts with a prefix."""
    if not src.exists():
        return
    for item in src.rglob("*"):
        rel = item.relative_to(src).as_posix()
        if any(rel.startswith(p) for p in exclude_prefixes):
            continue
        if drop_tests and _is_test_artifact(rel, item):
            continue
        target = dst / item.relative_to(src)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _exclude_dirs() -> tuple[str, ...]:
    return (
        "__pycache__/",
        ".pytest_cache/",
        "tests/",
        "test/",
        "venv/",
        ".venv/",
        "node_modules/",
        ".git/",
        "dist/",
        "release/",
        "data/",
        ".env",
        "*.pyc",
        "*.log",
    )


def _find_python() -> tuple[Path, Path]:
    """Return (base_python_exe, base_dir). Uses the REAL base interpreter
    (sys._base_executable) so we clone a fully self-contained runtime rather
    than a venv launcher that would still depend on the base install."""
    base_exe = getattr(sys, "_base_executable", None) or sys.executable
    base_exe = Path(base_exe).resolve()
    if not base_exe.exists():
        raise RuntimeError(f"Base interpreter not found: {base_exe}")
    return base_exe, base_exe.parent


def _locate_stdlib(base_exe: Path) -> Path:
    """Return the stdlib root that contains os.py for the given interpreter."""
    probe = subprocess.run(
        [str(base_exe), "-c", "import os; print(os.path.dirname(os.__file__))"],
        capture_output=True, text=True, check=True,
    )
    return Path(probe.stdout.strip())


def _locate_site_packages(exe: Path) -> Path:
    """Return the venv's site-packages (all runtime deps)."""
    probe = subprocess.run(
        [str(exe), "-c", "import site; print([p for p in site.getsitepackages() if 'site-packages' in p][0])"],
        capture_output=True, text=True, check=True,
    )
    return Path(probe.stdout.strip())


def build_python(portable: Path, base_exe: Path, base_dir: Path) -> None:
    _log("Bundling portable Python runtime...")
    stdlib = _locate_stdlib(base_exe)

    py_dst = portable / "python"
    py_dst.mkdir(parents=True, exist_ok=True)

    # Core interpreter binaries
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python312.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        p = base_dir / name
        if p.exists():
            shutil.copy2(p, py_dst / name)

    # Native extension modules (DLLs/*.pyd)
    dll_src = base_dir / "DLLs"
    if dll_src.exists():
        _copy_tree(dll_src, py_dst / "DLLs")

    # Standard library (must be on-disk: os.py, etc.)
    _copy_tree(stdlib, py_dst / "Lib", exclude_prefixes=("site-packages/", "test/"))

    _log(f"  stdlib: {stdlib}")
    _log(f"  native DLLs: {dll_src if dll_src.exists() else 'n/a'}")


def build_site_packages(portable: Path, exe: Path) -> None:
    _log("Bundling Python site-packages (deps)...")
    site_packages = _locate_site_packages(exe)
    dst = portable / "python" / "Lib" / "site-packages"
    dst.mkdir(parents=True, exist_ok=True)
    _copy_tree(site_packages, dst, exclude_prefixes=_exclude_dirs(), drop_tests=True)
    _log(f"  site-packages: {site_packages}")


def build_backend_source(portable: Path) -> None:
    _log("Bundling application source (api/ + app/)...")
    backend = portable / "backend"
    for sub in ("api", "app"):
        _copy_tree(REPO_ROOT / sub, backend / sub, exclude_prefixes=_exclude_dirs())
    # requirements for documentation/debug only — not used at runtime
    shutil.copy2(REPO_ROOT / "requirements.txt", backend / "requirements.txt")


def build_whisper(portable: Path) -> None:
    _log("Bundling Whisper model...")
    whisper_dst = portable / "whisper" / "faster-whisper-base"
    whisper_dst.mkdir(parents=True, exist_ok=True)

    from faster_whisper.utils import download_model  # type: ignore
    try:
        model_dir = Path(download_model("base", local_files_only=True))
    except Exception:
        model_dir = _find_hf_cache_model()

    if not model_dir or not (model_dir / "model.bin").exists():
        raise RuntimeError(
            "Could not locate the Whisper 'base' model. Run the backend once so "
            "faster-whisper downloads it to the HuggingFace cache, then re-run "
            "this script."
        )
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        src = model_dir / name
        if src.exists():
            shutil.copy2(src, whisper_dst / name)
        else:
            raise RuntimeError(f"Whisper model missing required file: {src}")
    _log(f"  model: {model_dir}")


def _find_hf_cache_model() -> Path:
    """Fallback: scan the HuggingFace hub cache for faster-whisper-base."""
    hub = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))) / "hub"
    for candidate in hub.glob("models--Systran--faster-whisper-base/snapshots/*"):
        if (candidate / "model.bin").exists():
            return candidate
    return Path()


def build_frontend(portable: Path) -> None:
    _log("Copying frontend static export...")
    src = REPO_ROOT / "frontend" / "out"
    if not (src / "index.html").exists():
        raise RuntimeError(
            "frontend/out is missing. Run `npm run build:frontend` (inside frontend/) first."
        )
    _copy_tree(src, portable / "frontend" / "out")
    _log("  frontend/out copied")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip", nargs="*", default=[], choices=["python", "whisper", "frontend"],
                    help="Skip sub-steps (useful for iterative packaging).")
    args = ap.parse_args()

    if PORTABLE_ROOT.exists():
        shutil.rmtree(PORTABLE_ROOT)
    PORTABLE_ROOT.mkdir(parents=True, exist_ok=True)

    exe = Path(sys.executable)
    base_exe, base_dir = _find_python()
    _log(f"Running venv python: {exe}")
    _log(f"Base interpreter:    {base_exe}")

    if "python" not in args.skip:
        build_python(PORTABLE_ROOT, base_exe, base_dir)
        build_site_packages(PORTABLE_ROOT, exe)
    build_backend_source(PORTABLE_ROOT)

    if "whisper" not in args.skip:
        build_whisper(PORTABLE_ROOT)

    if "frontend" not in args.skip:
        build_frontend(PORTABLE_ROOT)

    _log(f"DONE -> {PORTABLE_ROOT}")
    total = sum(f.stat().st_size for f in PORTABLE_ROOT.rglob("*") if f.is_file())
    _log(f"Bundle size: {total / (1024 * 1024):.1f} MB")


if __name__ == "__main__":
    main()
