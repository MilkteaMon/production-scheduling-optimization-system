"""Prepare an allowlisted standalone source snapshot; never operate Git or publish."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ["backend", "frontend", "data", "experiments", "docs/opspilot"]
EXCLUDED_PARTS = {
    ".venv",
    "node_modules",
    "dist",
    "test-results",
    "playwright-report",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    ".git",
}
EXTENSIONS = {
    ".py",
    ".toml",
    ".lock",
    ".json",
    ".jsonl",
    ".ini",
    ".mako",
    ".md",
    ".ts",
    ".tsx",
    ".css",
    ".html",
    ".js",
    ".mjs",
    ".csv",
    ".xml",
    ".txt",
    ".png",
    ".svg",
}


def build_bundle():
    files: dict[str, bytes] = {}
    for folder in FOLDERS:
        for path in (ROOT / folder).rglob("*"):
            relative = path.relative_to(ROOT)
            if (
                path.is_file()
                and not EXCLUDED_PARTS.intersection(relative.parts)
                and path.suffix in EXTENSIONS
                and path.name not in {".env", "tsconfig.tsbuildinfo"}
            ):
                files[relative.as_posix()] = path.read_bytes()
    for name in ["Dockerfile", "compose.yaml", ".dockerignore", "LICENSE", "AI_ASSISTANCE.md"]:
        files[name] = (ROOT / name).read_bytes()
    files[".github/workflows/opspilot.yml"] = (ROOT / ".github/workflows/opspilot.yml").read_bytes()
    for path in (ROOT / "scripts").glob("opspilot_*"):
        if path.is_file() and path.suffix in {".py", ".mjs"}:
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    readme = (ROOT / "PRODUCTION_SCHEDULING_README.md").read_text(encoding="utf-8")
    readme = readme.replace(
        "This workspace also contains an independently maintained engineering portfolio at the repository\n"
        "root. This production scheduling system lives in `backend/` and `frontend/` and uses its own\n"
        "dependency locks and checks.\n",
        "This standalone snapshot contains the scheduling system's backend, Web dashboard, dependency locks and checks.\n",
    )
    files["README.md"] = readme.encode("utf-8")
    files["PRODUCTION_SCHEDULING_README.md"] = readme.encode("utf-8")
    files[".gitignore"] = (ROOT / ".gitignore").read_bytes()
    files[".env.example"] = (
        "AI_ENABLED=false\nOPENAI_API_KEY=\nOPENAI_MODEL=\nOPENAI_AGENTS_DISABLE_TRACING=true\n"
        "CBC_PATH=\n# DATABASE_URL=sqlite:///runtime/opspilot.db\n"
    ).encode("utf-8")
    assert not any(
        key.startswith(("app/", "week9-work/", "runtime/")) or ".git/" in key for key in files
    )
    receipt = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "purpose": "Standalone source snapshot for the owner's manual GitHub workflow",
        "application": "Production Scheduling Optimization System",
        "git_operations_performed": False,
        "excluded": [
            "portfolio",
            "coursework",
            "Git history",
            "credentials",
            "databases",
            "runtime",
            "installed dependencies",
            "built frontend",
        ],
        "files": {key: hashlib.sha256(value).hexdigest() for key, value in sorted(files.items())},
    }
    output = ROOT / "runtime" / "distribution"
    output.mkdir(parents=True, exist_ok=True)
    target = output / "production-scheduling-optimization-system-source.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for key, value in sorted(files.items()):
            archive.writestr(key, value)
        archive.writestr("SOURCE_MANIFEST.json", json.dumps(receipt, indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for key, digest in receipt["files"].items():
            assert hashlib.sha256(archive.read(key)).hexdigest() == digest
    print(json.dumps({"path": str(target), "files": len(files), "bytes": target.stat().st_size}))


if __name__ == "__main__":
    build_bundle()
