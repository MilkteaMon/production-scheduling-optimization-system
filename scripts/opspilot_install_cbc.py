"""Optional official CBC distribution for Windows, without changing security settings."""

import hashlib
import json
import os
import urllib.request
import zipfile
from pathlib import Path

URL = "https://github.com/coin-or/Cbc/releases/download/releases/2.10.13/Cbc-releases.2.10.13-windows-2025-msvs-v17-Release-x64.zip"

if os.name != "nt":
    raise SystemExit("Use the locked pulp[cbc] distribution on Linux")
root = Path(__file__).resolve().parents[1] / "runtime" / "solvers"
root.mkdir(parents=True, exist_ok=True)
archive = root / "cbc-official.zip"
if not archive.exists():
    urllib.request.urlretrieve(URL, archive)
with zipfile.ZipFile(archive) as file:
    for entry in file.infolist():
        if not (root / entry.filename).resolve().is_relative_to(root.resolve()):
            raise ValueError("Unsafe archive entry")
    for entry in file.infolist():
        destination = root / entry.filename
        if entry.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif not destination.is_file() or destination.read_bytes() != file.read(entry):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(file.read(entry))
(root / "source.json").write_text(
    json.dumps(
        {
            "source_url": URL,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "cbc_release": "2.10.13",
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Installed official CBC in runtime/solvers. No security policy was changed.")
