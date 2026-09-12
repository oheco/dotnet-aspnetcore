# .NET 10 / ASP.NET Core for HarmonyOS PC ARM64

The SDK distribution provides .NET SDK 10.0.401, .NET Runtime 10.0.12 and
ASP.NET Core 10.0.12. The standalone ASP.NET runtime distribution includes
both runtime frameworks and provides `aspnetcore-runtime`.

Install through the official oheco package index:

```sh
oo update
oo install dotnet-sdk
dotnet --list-runtimes
dotnet new web -o HelloWeb
cd HelloWeb
dotnet run --no-launch-profile --urls http://127.0.0.1:5000
```

For deployment without the SDK:

```sh
oo install aspnetcore-runtime
aspnetcore-runtime /path/to/MyWebApp.dll --urls http://127.0.0.1:5000
```

Publish a self-contained application on the host:

```sh
dotnet publish -c Release -r openharmony-arm64 --self-contained true
dotnet publish -c Release -r openharmony-arm64 -p:PublishReadyToRun=true
```

For NativeAOT, create an upstream-supported Minimal API project, such as
`dotnet new webapiaot`, and publish with `-r openharmony-arm64`. NativeAOT
requires the host LLVM tools and `binary-sign-tool` on PATH. The SDK signs
new executable outputs automatically. MVC/Razor/SignalR applications use
the normal CoreCLR runtime; upstream NativeAOT feature limits still apply.

The archive may be unpacked and moved as a whole, including into a path
containing spaces. Use its `bin/dotnet` or `bin/aspnetcore-runtime` launcher
when running outside the package manager. Keep the supplied libraries beside
the runtime; no `LD_LIBRARY_PATH` changes or manual re-signing are required.

The launcher selects an application-private temporary directory. Override
`DOTNET_OHOS_TMPDIR` for a different application layout. Configure writable
content, upload, logging and Data Protection key locations for your service.
Use your own TLS certificate for deployment. Package restore needs access to
the appropriate NuGet feeds; configure your network proxy when required.

HTTP/1.1, HTTPS/HTTP/2, WebSocket, MVC/Razor, SignalR and managed gRPC are covered
by the native acceptance suite. HTTP/3 is unavailable without a compatible
MsQuic native dependency. Windows IIS/HTTP.sys, Kerberos/GSSAPI, GUI workloads,
phone sandbox deployment and native Grpc.Tools/protoc are outside the
validated support described by this release. Automatic system certificate
trust integration is not validated.

Sources and detailed evidence: https://github.com/oheco/dotnet-aspnetcore,
https://github.com/oheco/dotnet-sdk and https://github.com/oheco/dotnet-runtime.
See `BUILDINFO.aspnetcore.json` and the Release validation record for exact
source commits, artifact hashes and tested environment. The inherited Microsoft
license notices are in this archive and `licenses/`; this is a community port.
