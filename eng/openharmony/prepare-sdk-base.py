#!/usr/bin/env python3
"""Recreate the exact prior Runtime/MSBuild SDK input feed offline."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import xml.etree.ElementTree as ET

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("upstream_cache", type=Path)
p.add_argument("target_archive", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
kit = Path(__file__).resolve().parent
fixed = json.loads((kit / "sdk-target-input-archive.json").read_text())
with a.target_archive.open("rb") as f:
    digest = hashlib.file_digest(f, "sha256").hexdigest()
if a.target_archive.stat().st_size != fixed["size"] or digest != fixed["sha256"]:
    raise ValueError("SDK target input archive checksum mismatch")
a.output.mkdir(parents=True, exist_ok=False)
with tarfile.open(a.target_archive) as archive:
    archive.extractall(a.output, filter="data")
records = json.loads((kit / "sdk-base-inputs.json").read_text())
for item in records:
    target = a.output / item["path"]
    if not target.exists():
        source = a.upstream_cache / item["archive"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    with target.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if target.stat().st_size != item["size"] or digest != item["sha256"]:
        raise ValueError("SDK input checksum mismatch: " + item["path"])
config = ET.Element("configuration")
sources = ET.SubElement(config, "packageSources")
ET.SubElement(sources, "clear")
ET.SubElement(sources, "add", key="fixed-inputs", value=str((a.output / "packages").resolve()))
ET.indent(config)
ET.ElementTree(config).write(a.output / "NuGet.Config", encoding="utf-8", xml_declaration=True)
shutil.copyfile(kit / "sdk-base-inputs.json", a.output / "manifest.json")
print("Verified", len(records), "SDK base inputs")
