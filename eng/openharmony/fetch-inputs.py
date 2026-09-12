#!/usr/bin/env python3
"""Explicit online preparation; source builds never download these inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("downloads", type=Path)
a = p.parse_args()
a.downloads.mkdir(parents=True, exist_ok=True)
proxy = os.environ.get("DOTNET_OHOS_PROXY", "socks5h://127.0.0.1:10808")
if not proxy:
    p.error("A proxy is required")
kit = Path(__file__).resolve().parent
for item in json.loads((kit / "base-inputs.json").read_text())["archives"]:
    target = a.downloads / item["archive"]
    candidate = target
    if not target.exists():
        candidate = target.with_name(target.name + ".partial")
        subprocess.run(["curl", "--proxy", proxy, "--noproxy", "", "--fail", "--location",
                        "--retry", "3", "--connect-timeout", "20", "--max-time", "1800",
                        "--proto", "=https", "--proto-redir", "=https",
                        "--output", str(candidate), item["url"]], check=True)
    with candidate.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if candidate.stat().st_size != item["size"] or digest != item["sha256"]:
        raise ValueError("Archive integrity check failed: " + candidate.name)
    if candidate != target:
        candidate.replace(target)
    print("Verified", target.name, flush=True)
