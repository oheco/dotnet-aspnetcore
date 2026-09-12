# ASP.NET Core 10 on OpenHarmony ARM64

This port targets the HarmonyOS PC command-line environment. It builds
Microsoft.AspNetCore.App 10.0.12 from the upstream v10.0.12 baseline
`cb21a42eafcd44cc35fad48d99dc82ff7512ce2f`, with an independent
`openharmony-arm64` runtime pack and Unix ARM64 ReadyToRun code generation.
The adaptation repository is https://github.com/oheco/dotnet-aspnetcore;
its branch is `ohos/10.0.12`.

The standalone ASP.NET runtime distribution includes .NET Runtime 10.0.12.
The SDK integration targets https://github.com/oheco/dotnet-sdk,
branch `ohos/10.0.401`, and bundles the framework, targeting/runtime packs,
Web templates, analyzers, static assets and developer tools. The SDK owns
`dotnet`; the standalone package owns `aspnetcore-runtime`.

## Fixed inputs and offline build

Use Linux ARM64 with Git, Python 3.11+, Bash and tar. Extract tools and build
on a Linux filesystem; the shared host mount does not implement all Unix
directory metadata operations. Signing and final acceptance require the real
HarmonyOS host, its LLVM tools, and `binary-sign-tool` on PATH.

`base-inputs.json` fixes every bootstrap/archive URL, size, SHA-256 and license.
It includes Linux SDK 10.0.111, Node 24.15.0, the prior published OpenHarmony
SDK/Runtime, the exact MessagePack-CSharp submodule source, and immutable
NuGet/npm input bundles. Original NuGet archives and npm package tarballs
retain their component licenses. `nuget-inputs.json` and `npm-inputs.json`
describe the individual dependencies. These are build dependency inventories,
not lists of files shipped in the runtime.

Download separately, then prepare a fresh, unpopulated source checkout:

```sh
export DOTNET_OHOS_PROXY=socks5h://127.0.0.1:10808
python3 eng/openharmony/fetch-inputs.py /path/to/downloads
python3 eng/openharmony/prepare-inputs.py /path/to/downloads \
  /tmp/aspnetcore-source /tmp/aspnetcore-inputs
python3 /tmp/aspnetcore-source/eng/openharmony/build-release.py \
  /tmp/aspnetcore-source /tmp/aspnetcore-inputs /path/to/new-build-logs
```

Preparation verifies the archives, extracts the pinned source submodule and
Linux tools, and seeds an isolated NuGet cache. The build uses a local-only
NuGet configuration and `npm ci --offline`. Its inputs include the functional
test workspace's type definitions because the upstream SignalR compiler
configuration imports them; browser tests are not run during packaging.
No upstream dependency versions are re-resolved during the source build.

The previous OpenHarmony SDK is a bootstrap dependency. Only its managed
MSBuild resolver and RID graph run on Linux; target ELF programs are never
executed on the build machine. The resolver preserves the OpenHarmony runtime
pack while selecting the Unix ARM64 code-generation ABI.

Output packs are in `artifacts/packages/Release`. The shared framework is in
`artifacts/obj/SharedFx.Layout/Release/openharmony-arm64/shared/`.
The fixed build stamp is `20260912.1`; internal tool/analyzer versions are
`10.0.12-servicing.26462.1`. Build logs record the source commit and hashes.

The generic archive, signing, ELF verification and NuGet helper scripts were
copied from oheco/dotnet-runtime commit
`db44ddccf3a0665b7a0a3d4b1acc4b6e8917efc6` under its MIT license.
The base runtime binary provenance remains
`033589b2981f30e657b283f54a3697c5d124fc3b`; SDK ohos.1 bootstrap provenance
is recorded alongside its archive in `base-inputs.json`.

## Acceptance and limits

`acceptance/` contains ordinary consumer projects, isolated from the repository
build. WebSmoke checks HTTP/1.1, HTTPS and HTTP/2 ALPN, JSON, upload buffering
and temporary-file cleanup, gzip, fragmented WebSocket messages, error
responses, concurrency/cancellation, malformed HTTP, persisted Data Protection
keys, MVC/compiled Razor views, Razor Pages, static files and SignalR.
GrpcSmoke checks a real unary gRPC call over HTTPS/HTTP/2 using pinned managed
gRPC 2.64.0 packages. AotSmoke uses the same protocol checks with the supported
ASP.NET NativeAOT Minimal API hosting model and JSON source generation.

NativeAOT support follows upstream ASP.NET Core constraints: the validated
model is Minimal API, while MVC/Razor/SignalR are validated with the normal
runtime. A successful native acceptance applies to the tested HarmonyOS PC
environment; it does not establish support for phone application sandboxes.

HTTP/3 requires a separate working MsQuic native dependency, which is not
bundled; QUIC currently reports unsupported. IIS and HTTP.sys are upstream
Windows-only servers. Kerberos/GSSAPI follows the base runtime's documented
limit. No GUI workloads or browser WebAssembly native toolchain are included.
The gRPC test uses explicit service bindings and does not claim support for
executing foreign Grpc.Tools/protoc binaries on the host.

Use an application-private temporary directory (the packaged launcher provides
one; `DOTNET_OHOS_TMPDIR` overrides it). Configure a writable content root,
uploads, logs and Data Protection key directory for your application. Supply
your own production TLS certificate. System-wide development-certificate
trust integration is outside the validated scope.

Release evidence must distinguish preliminary development overlays from the
fresh, signed installation and official-index acceptance. See the published
release's validation record for the final artifact hashes and native results.

## SDK rebuild and distribution

The additional SDK recipe uses Linux SDK 10.0.302 and fixed .NET 6–9 build-tool
frameworks from `sdk-build-tools.json`. Download those with
`fetch-inputs.py <downloads> --manifest sdk-build-tools.json`, then run
`prepare-sdk-tools.py <downloads> <new-linux-tool-directory>`.

The 860 upstream SDK/MSBuild dependency archives are fixed in
`sdk-upstream-inputs.json`; use `fetch-nuget-inputs.py <manifest> <cache>`
through the configured proxy. Obtain the archive described in
`sdk-target-input-archive.json` from the SDK ohos.2 Release. It contains the
17 exact prior Runtime/MSBuild target inputs, including the target runtime
archive, their original licenses and the base manifest. Recreate and verify the
complete base with `prepare-sdk-base.py <upstream-cache> <target-input-archive>
<new-base-feed>`. The prior Runtime and MSBuild source-build recipes remain
available in their adaptation repositories at the provenance commits.

After the ASP.NET source build:

```sh
python3 prepare-sdk-feed.py /path/to/base-feed /tmp/aspnetcore-source /tmp/sdk-feed
export DOTNET_INSTALL_DIR=/tmp/sdk-build-tools
export NUGET_PACKAGES=/tmp/sdk-empty-cache
export DOTNET_CLI_HOME=/tmp/sdk-cli
python3 seed-nuget-cache.py "$DOTNET_INSTALL_DIR/dotnet" /tmp/sdk-feed/manifest.json \
  /tmp/sdk-feed /tmp/sdk-seed /path/to/sdk-seed.log
bash build-sdk-release.sh /tmp/fresh-sdk-source /tmp/sdk-feed /path/to/sdk-build.log
```

The SDK source must contain the ASP.NET integration described in
`oheco/dotnet-sdk/eng/openharmony/ASP.NET.md`. All layout components are built
by the normal source graph; no hand-copied Web SDK entry files are used in the
release. `prepare-sdk-feed.py` records the ASP.NET source commit and archive
hashes alongside the fixed base dependencies.

`stage-distribution.py runtime <built-aspnet-source> <published-base-runtime-tar>
<new-shared-stage>` composes the standalone package, preserving the signed base
runtime. For the SDK, use `sdk` and add `--sdk-layout <redist/dotnet-installer>
--sdk-source <sdk-source>`. The copier retains internal symlinks and avoids
unsupported directory metadata operations on the shared mount.

On the native host, sign the staged SDK using `sign-tree.zsh <stage> <logs>`;
make the launchers executable. Use `package-tree.py` to preserve signed bytes
and normalize execution permissions in a GNU-format tar archive. Extract both
archives into fresh private directories with spaces in their names. Run
`accept-web.zsh <sdk-root> <asp-runtime-root> <new-private-run-directory>`
against these relocated trees. It checks all publish modes, the standalone
runtime, gRPC, five standard Web templates including Blazor static framework
assets, and developer tools without changing the user's certificate store or
secret files. Existing console/MSBuild/native-AOT regression acceptance is
provided by the Runtime repository's `accept-sdk.zsh`.

Final publication includes immutable package archives, SHA-256 sums, source
provenance and native acceptance evidence. Catalogue installation must then be
verified using the official online index in an isolated `oo` root; a successful
source build or development overlay is not considered a delivered version.
