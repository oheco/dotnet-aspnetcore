#!/usr/bin/env python3
"""Prepare pinned Linux SDK build tools without executing target programs."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("downloads", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
kit = Path(__file__).resolve().parent
records = json.loads((kit / "sdk-build-tools.json").read_text())["archives"]
for item in records:
    archive = a.downloads / item["archive"]
    with archive.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if archive.stat().st_size != item["size"] or digest != item["sha256"]:
        raise ValueError("SDK build tool checksum mismatch: " + archive.name)
a.output.mkdir(parents=True, exist_ok=False)
for item in records:
    with tarfile.open(a.downloads / item["archive"]) as archive:
        members = archive.getmembers()
        if item["name"] == "dotnet-runtime-linux-arm64":
            prefix = Path("shared/Microsoft.NETCore.App") / item["version"]
            members = [m for m in members if Path(m.name).is_relative_to(prefix)]
        archive.extractall(a.output, members=members, filter="data")
print("Prepared verified SDK build tools", a.output)
