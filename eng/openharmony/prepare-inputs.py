#!/usr/bin/env python3
"""Verify release inputs and prepare an isolated offline ASP.NET build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("downloads", type=Path)
p.add_argument("source", type=Path, help="Fresh adaptation checkout")
p.add_argument("output", type=Path, help="New Linux filesystem directory")
a = p.parse_args()
kit = Path(__file__).resolve().parent
records = json.loads((kit / "base-inputs.json").read_text())["archives"]
for item in records:
    archive = a.downloads / item["archive"]
    with archive.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    if archive.stat().st_size != item["size"] or digest != item["sha256"]:
        raise ValueError("Input checksum mismatch: " + archive.name)
a.output.mkdir(parents=True, exist_ok=False)
a.output = a.output.resolve()
by_name = {item["name"]: a.downloads / item["archive"] for item in records}

def extract(name, destination, strip=0):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(by_name[name]) as archive:
        members = archive.getmembers()
        for member in members:
            if strip:
                member.name = "/".join(Path(member.name).parts[strip:])
        archive.extractall(destination, members=[m for m in members if m.name], filter="data")

extract("dotnet-sdk-linux-arm64", a.output / "dotnet")
extract("node-linux-arm64", a.output / "node", 1)
extract("aspnetcore-nuget-inputs", a.output / "nuget-archives")
extract("aspnetcore-npm-inputs", a.output / "npm-cache")
submodule = a.source / "src/submodules/MessagePack-CSharp"
if submodule.exists() and any(submodule.iterdir()):
    raise ValueError("Use an unpopulated source submodule directory")
extract("MessagePack-CSharp", submodule, 1)
subprocess.run(["python3", str(kit / "prepare-bootstrap.py"), str(a.downloads),
                str(a.output / "helpers")], check=True)
subprocess.run(["python3", str(kit / "nuget-inputs.py"), "stage",
                str(a.output / "nuget-archives"), str(kit / "nuget-inputs.json"),
                "--destination", str(a.output / "feed")], check=True)
env = dict(os.environ, NUGET_PACKAGES=str(a.output / "nuget"),
           DOTNET_CLI_HOME=str(a.output / "cli"), DOTNET_CLI_TELEMETRY_OPTOUT="1",
           DOTNET_GENERATE_ASPNET_CERTIFICATE="false")
subprocess.run(["python3", str(kit / "seed-nuget-cache.py"),
                str(a.output / "dotnet/dotnet"), str(kit / "nuget-inputs.json"),
                str(a.output / "feed"), str(a.output / "seed"),
                str(a.output / "seed.log")], env=env, check=True)
print("Prepared verified offline inputs:", a.output)
