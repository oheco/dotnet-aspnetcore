#!/usr/bin/env python3
"""Compose a relocatable distribution for final native signing and acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("kind", choices=["runtime", "sdk"])
p.add_argument("source", type=Path, help="Built ASP.NET source")
p.add_argument("runtime_archive", type=Path, help="Pinned published base Runtime archive")
p.add_argument("output", type=Path, help="New shared staging directory")
p.add_argument("--sdk-layout", type=Path)
p.add_argument("--sdk-source", type=Path)
a = p.parse_args()
kit = Path(__file__).resolve().parent
fixed = next(x for x in json.loads((kit / "base-inputs.json").read_text())["archives"] if x["name"] == "openharmony-runtime")
with a.runtime_archive.open("rb") as f:
    digest = hashlib.file_digest(f, "sha256").hexdigest()
if a.runtime_archive.stat().st_size != fixed["size"] or digest != fixed["sha256"]:
    raise ValueError("Base Runtime checksum mismatch")
a.output.mkdir(parents=True, exist_ok=False)

def copy_tree(source, target):
    source = source.resolve(strict=True)
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        dest = target / path.relative_to(source)
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(source):
                raise ValueError("Installation symlink leaves its tree: " + str(path))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.symlink_to(os.path.relpath(target / resolved.relative_to(source), dest.parent))
        elif path.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
        else:
            raise ValueError("Unexpected installation entry: " + str(path))

with tempfile.TemporaryDirectory(prefix="aspnet-base-runtime-") as temporary:
    with tarfile.open(a.runtime_archive) as archive:
        archive.extractall(temporary, filter="data")
    base = next(Path(temporary).iterdir())
    if a.kind == "runtime":
        copy_tree(base, a.output)
        old = a.output / "bin/dotnet-runtime"
        old.unlink()
        framework = a.source / "artifacts/obj/SharedFx.Layout/Release/openharmony-arm64/shared/Microsoft.AspNetCore.App"
        copy_tree(framework, a.output / "shared/Microsoft.AspNetCore.App")
    else:
        if not a.sdk_layout or not a.sdk_source:
            p.error("SDK staging requires --sdk-layout and --sdk-source")
        copy_tree(a.sdk_layout, a.output)
        copy_tree(base / "licenses", a.output / "licenses")
        msbuild = a.sdk_source / "tpr/msbuild"
        for name in ["LICENSE", "THIRDPARTYNOTICES.txt"]:
            if not (msbuild / name).is_file():
                raise ValueError("Missing MSBuild license input: " + str(msbuild / name))
            shutil.copyfile(msbuild / name, a.output / "licenses" / ("MSBuild-" + name))

launcher = "dotnet" if a.kind == "sdk" else "aspnetcore-runtime"
(a.output / "bin").mkdir(exist_ok=True)
shutil.copyfile(kit / "launch-dotnet.sh", a.output / "bin" / launcher)
(a.output / "licenses").mkdir(exist_ok=True)
for name in ["LICENSE.txt", "THIRD-PARTY-NOTICES.txt"]:
    shutil.copyfile(a.source / name, a.output / "licenses" / ("ASP.NET-" + name))
shutil.copyfile(a.source / "src/submodules/MessagePack-CSharp/LICENSE", a.output / "licenses/MessagePack-CSharp-LICENSE")
shutil.copyfile(kit / "install.md", a.output / "README.openharmony.md")
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=a.source, text=True).strip()
info = dict(kind=a.kind, aspnet_version="10.0.12", runtime_version="10.0.12",
            aspnet_source_commit=commit, runtime_archive_sha256=fixed["sha256"],
            runtime_source_commit=fixed["source_commit"], rid="openharmony-arm64")
if a.kind == "sdk":
    info.update(sdk_version="10.0.401", sdk_source_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=a.sdk_source, text=True).strip())
(a.output / "BUILDINFO.aspnetcore.json").write_text(json.dumps(info, indent=2) + "\n")
if not (a.output / "shared/Microsoft.AspNetCore.App/10.0.12/Microsoft.AspNetCore.App.deps.json").is_file():
    raise ValueError("Missing ASP.NET shared framework")
print("Staged", a.kind, "at", a.output, "; native signing/acceptance still required")
