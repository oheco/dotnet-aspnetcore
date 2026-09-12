#!/usr/bin/env python3
"""Build ASP.NET Core and SDK inputs in a fresh checkout without downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("source", type=Path)
p.add_argument("inputs", type=Path)
p.add_argument("logs", type=Path)
a = p.parse_args()
a.source = a.source.resolve(strict=True)
a.inputs = a.inputs.resolve(strict=True)
kit = a.source / "eng/openharmony"
if (a.source / "artifacts").exists():
    p.error("Use a fresh source checkout without artifacts")
a.logs.mkdir(parents=True, exist_ok=False)
a.logs = a.logs.resolve()
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=a.source, text=True).strip()
env = dict(os.environ, NUGET_PACKAGES=str(a.inputs / "nuget"),
           DOTNET_CLI_HOME=str(a.inputs / "cli"), DOTNET_CLI_TELEMETRY_OPTOUT="1",
           DOTNET_GENERATE_ASPNET_CERTIFICATE="false", MSBUILDDISABLENODEREUSE="1",
           PATH=str(a.inputs / "node/bin") + os.pathsep + os.environ["PATH"])

def run(label, command):
    (a.logs / (label + ".command.json")).write_text(json.dumps(command, indent=2) + "\n")
    print("START", label, flush=True)
    with (a.logs / (label + ".log")).open("x") as log:
        subprocess.run(command, cwd=a.source, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True)
    print("PASS", label, flush=True)

run("javascript", ["bash", str(kit / "build-js.sh"), str(a.source),
                   str(a.inputs / "npm-cache"), str(a.logs / "javascript-build.log")])
options = ["/p:DotNetBuild=true", "/p:Configuration=Release", "/p:TargetOsName=openharmony",
           "/p:TargetArchitecture=arm64", "/p:StabilizePackageVersion=true",
           "/p:OfficialBuildId=20260912.1", "/p:DotNetUseShippingVersions=true",
           "/p:NuGetAudit=false", "/p:UseSharedCompilation=false", "/m:2", "/nr:false",
           "/p:SourceRevisionId=" + commit, "/p:RepositoryCommit=" + commit,
           "/p:RestoreConfigFile=" + str(a.inputs / "feed/NuGet.Config"),
           "/p:OpenHarmonySdkBuildTasks=" + str(a.inputs / "helpers/sdk-tasks/Microsoft.NET.Build.Tasks.dll"),
           "/p:RuntimeIdentifierGraphPath=" + str(a.inputs / "helpers/PortableRuntimeIdentifierGraph.json")]

def msbuild(label, project, target="Build", extra=()):
    run(label, [str(a.inputs / "dotnet/dotnet"), "msbuild", project,
                "/restore", "/t:" + target, *options, *extra])

msbuild("generate-files", "eng/tools/GenerateFiles/GenerateFiles.csproj", "GenerateDirectoryBuildFiles")
msbuild("repo-tasks", "eng/tools/RepoTasks/RepoTasks.csproj")
msbuild("framework", "src/Framework/App.Runtime/src/Microsoft.AspNetCore.App.Runtime.sfxproj",
        extra=["/p:GenerateInstallers=false"])
msbuild("reference-pack", "src/Framework/App.Ref/src/Microsoft.AspNetCore.App.Ref.sfxproj",
        extra=["/p:GenerateInstallers=false"])
for name in ["dotnet-dev-certs", "dotnet-user-secrets", "dotnet-user-jwts"]:
    msbuild(name, f"src/Tools/{name}/src/{name}.csproj", "Pack", ["/p:UseAppHost=false"])
msbuild("static-assets", "src/Assets/Microsoft.AspNetCore.App.Internal.Assets.csproj",
        "Pack", ["/p:BuildNodeJS=true"])
for name in ["Web.ProjectTemplates", "Web.ItemTemplates", "Web.Client.ItemTemplates"]:
    msbuild(name, f"src/ProjectTemplates/{name}/Microsoft.DotNet.{name}.csproj", "Pack")
for name, project in [
    ("analyzers", "src/Analyzers/Analyzers/src/Microsoft.AspNetCore.Analyzers.csproj"),
    ("component-analyzers", "src/Tools/SDK-Analyzers/Components/src/Microsoft.AspNetCore.Components.SdkAnalyzers.csproj"),
    ("mvc-analyzers", "src/Mvc/Mvc.Analyzers/src/Microsoft.AspNetCore.Mvc.Analyzers.csproj"),
    ("mvc-api-analyzers", "src/Mvc/Mvc.Api.Analyzers/src/Microsoft.AspNetCore.Mvc.Api.Analyzers.csproj")]:
    msbuild(name, project, "Pack")
records = []
for archive in sorted((a.source / "artifacts/packages/Release").rglob("*.nupkg")):
    if archive.name.endswith(".symbols.nupkg"):
        continue
    with archive.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    records.append(dict(path=archive.relative_to(a.source).as_posix(),
                        size=archive.stat().st_size, sha256=digest))
(a.logs / "build.json").write_text(json.dumps(dict(source_commit=commit, packages=records), indent=2) + "\n")
print("Source build complete; native acceptance is still required.", flush=True)
