#!/usr/bin/env python3
"""Verify pinned archives and extract the prior SDK's managed build helpers.

No downloads occur here. The prior OpenHarmony SDK is a source-built bootstrap
input; only its managed task resolver and independent RID graph are used on the
Linux build machine. Its native executables are never run there.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("downloads", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
kit = Path(__file__).resolve().parent
records = json.loads((kit / "base-inputs.json").read_text())["archives"]
for item in records:
    archive = args.downloads / item["archive"]
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if archive.stat().st_size != item["size"] or digest != item["sha256"]:
        raise SystemExit("Input integrity check failed: " + archive.name)
args.output.mkdir(parents=True, exist_ok=False)
sdk = next(item for item in records if item["name"] == "openharmony-sdk")
files = []
with tarfile.open(args.downloads / sdk["archive"]) as archive:
    for member in archive.getmembers():
        relative = Path(*Path(member.name).parts[1:])
        tasks = Path("sdk/10.0.401/Sdks/Microsoft.NET.Sdk/tools/net10.0")
        if relative.is_relative_to(tasks):
            target = args.output / "sdk-tasks" / relative.relative_to(tasks)
        elif relative.as_posix() == "sdk/10.0.401/PortableRuntimeIdentifierGraph.json":
            target = args.output / "PortableRuntimeIdentifierGraph.json"
        else:
            continue
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
        elif member.isfile():
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = archive.extractfile(member).read()
            target.write_bytes(payload)
            files.append(dict(path=target.relative_to(args.output).as_posix(),
                              size=len(payload), sha256=hashlib.sha256(payload).hexdigest()))
        else:
            raise SystemExit("Unexpected bootstrap archive entry: " + member.name)
task = args.output / "sdk-tasks/Microsoft.NET.Build.Tasks.dll"
graph = args.output / "PortableRuntimeIdentifierGraph.json"
if not task.is_file() or "openharmony-arm64" not in json.loads(graph.read_text())["runtimes"]:
    raise SystemExit("Missing OpenHarmony bootstrap helpers")
(args.output / "manifest.json").write_text(json.dumps(files, indent=2) + "\n")
print(f"Verified {len(records)} archives and extracted {len(files)} bootstrap files")
