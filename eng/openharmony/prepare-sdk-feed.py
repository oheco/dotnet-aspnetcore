#!/usr/bin/env python3
"""Combine verified prior Runtime/MSBuild inputs and freshly built ASP.NET."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import zipfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("base_feed", type=Path)
p.add_argument("aspnet_source", type=Path)
p.add_argument("output", type=Path)
a = p.parse_args()
kit = Path(__file__).resolve().parent
records = json.loads((kit / "sdk-base-inputs.json").read_text())

def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

for item in records:
    archive = (a.base_feed / item["path"]).resolve(strict=True)
    if not archive.is_relative_to(a.base_feed.resolve()) or archive.stat().st_size != item["size"] or digest(archive) != item["sha256"]:
        raise ValueError("SDK base checksum mismatch: " + item["path"])
a.output.mkdir(parents=True, exist_ok=False)
for item in records:
    target = a.output / item["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.base_feed / item["path"], target)

required = {
    "microsoft.aspnetcore.app.ref", "microsoft.aspnetcore.app.runtime.openharmony-arm64",
    "microsoft.aspnetcore.app.internal.assets", "dotnet-dev-certs", "dotnet-user-jwts",
    "dotnet-user-secrets", "microsoft.dotnet.web.projecttemplates.10.0",
    "microsoft.dotnet.web.itemtemplates.10.0", "microsoft.aspnetcore.analyzers",
    "microsoft.aspnetcore.components.sdkanalyzers", "microsoft.aspnetcore.mvc.analyzers",
    "microsoft.aspnetcore.mvc.api.analyzers"}
found = set()
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=a.aspnet_source, text=True).strip()
for archive in sorted((a.aspnet_source / "artifacts/packages/Release").rglob("*.nupkg")):
    if archive.name.endswith(".symbols.nupkg"):
        continue
    with zipfile.ZipFile(archive) as z:
        root = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith(".nuspec") and "/" not in n)))
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    metadata = root.find("metadata")
    identifier = metadata.findtext("id").lower()
    version = metadata.findtext("version").lower()
    if identifier not in required:
        continue
    if version not in ("10.0.12", "10.0.12-servicing.26462.1"):
        raise ValueError("Unexpected ASP.NET package version: " + identifier)
    name = identifier + "." + version + ".nupkg"
    relative = "packages/" + name
    if (a.output / relative).exists():
        raise ValueError("Unexpected collision in base feed: " + name)
    shutil.copyfile(archive, a.output / relative)
    records.append(dict(id=identifier, version=version, origin="aspnetcore-source-build",
                        source_commit=commit, archive=name, path=relative,
                        size=archive.stat().st_size, sha256=digest(archive)))
    found.add(identifier)
if found != required:
    raise ValueError("Missing ASP.NET packages: " + str(required - found))
layout = a.aspnet_source / "artifacts/obj/SharedFx.Layout/Release/openharmony-arm64"
framework = layout / "shared/Microsoft.AspNetCore.App/10.0.12"
deps = json.loads((framework / "Microsoft.AspNetCore.App.deps.json").read_text())
if not deps["runtimeTarget"]["name"].endswith("/openharmony-arm64"):
    raise ValueError("Wrong ASP.NET target RID")
name = "aspnetcore-runtime-10.0.12-openharmony-arm64.tar.gz"
target = a.output / "downloads" / name
with tarfile.open(target, "w:gz", format=tarfile.GNU_FORMAT) as archive:
    archive.add(framework, arcname="shared/Microsoft.AspNetCore.App/10.0.12")
records.append(dict(id="aspnetcore-runtime-archive", version="10.0.12",
                    origin="aspnetcore-source-build", source_commit=commit, archive=name,
                    path="downloads/" + name, size=target.stat().st_size, sha256=digest(target)))
config = ET.Element("configuration")
sources = ET.SubElement(config, "packageSources")
ET.SubElement(sources, "clear")
ET.SubElement(sources, "add", key="fixed-inputs", value=str((a.output / "packages").resolve()))
ET.indent(config)
ET.ElementTree(config).write(a.output / "NuGet.Config", encoding="utf-8", xml_declaration=True)
(a.output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n")
print("Prepared", len(records), "SDK inputs including", len(found), "ASP.NET source-built packages")
