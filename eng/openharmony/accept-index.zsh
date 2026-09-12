#!/usr/bin/zsh
# Execute only after immutable Releases and the official Pages index are live.
set -eu
(( $# == 2 )) || { print -u2 'Usage: accept-index.zsh oo-executable new-private-directory'; exit 2; }
index_oo=${1:A}
index_root=${2:A}
index_kit=${0:A:h}
[[ ! -e $index_root && -x $index_oo ]]
mkdir -p "$index_root/tmp" "$index_root/cli" "$index_root/nuget"
export OHECO_ROOT="$index_root/installation with spaces"
export OHECO_INDEX_URL=https://oheco.github.io/oheco-packages/index/v3/index.json
export OHECO_NO_AUTO_UPDATE=1
export DOTNET_OHOS_TMPDIR="$index_root/tmp" TMPDIR="$index_root/tmp"
export DOTNET_CLI_HOME="$index_root/cli" NUGET_PACKAGES="$index_root/nuget"
export DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_CLI_TELEMETRY_OPTOUT=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://172.16.105.2:10808}
export HTTPS_PROXY=$HTTP_PROXY NO_PROXY= no_proxy=
export PATH="$OHECO_ROOT/bin:$PATH"
unset LD_LIBRARY_PATH DOTNET_ROOT DOTNET_ROOT_ARM64
index_sdk=10.0.401-ohos.2
index_asp=10.0.12-ohos.1
index_run() {
    local index_name=$1
    shift
    print -r -- "RUN $index_name"
    if "$@" > "$index_root/$index_name.log" 2>&1; then
        print -r -- "PASS $index_name"
    else
        local index_rc=$?
        cat "$index_root/$index_name.log"
        return $index_rc
    fi
}
index_shutdown() {
    if [[ -x "$OHECO_ROOT/bin/dotnet" ]]; then
        "$OHECO_ROOT/bin/dotnet" build-server shutdown > "$index_root/shutdown.log" 2>&1 || true
    fi
}
trap index_shutdown EXIT
index_run update "$index_oo" update
index_run install-sdk "$index_oo" install dotnet-sdk
index_run install-aspnet "$index_oo" install aspnetcore-runtime
[[ -d "$OHECO_ROOT/packages/dotnet-sdk/$index_sdk" ]]
[[ -d "$OHECO_ROOT/packages/aspnetcore-runtime/$index_asp" ]]
index_run sdk-version "$OHECO_ROOT/bin/dotnet@$index_sdk" --version
[[ $(< "$index_root/sdk-version.log") == 10.0.401 ]]
index_run asp-version "$OHECO_ROOT/bin/aspnetcore-runtime@$index_asp" --list-runtimes
[[ $(< "$index_root/asp-version.log") == *'Microsoft.AspNetCore.App 10.0.12 '* ]]
cp -R "$index_kit/acceptance" "$index_root/source with spaces"
cd "$index_root/source with spaces"
index_run build-web dotnet build WebSmoke/WebSmoke.csproj -c Release --disable-build-servers
index_run sdk-web dotnet WebSmoke/bin/Release/net10.0/WebSmoke.dll "$index_root/sdk-state"
index_run standalone-web "$OHECO_ROOT/bin/aspnetcore-runtime@$index_asp" WebSmoke/bin/Release/net10.0/WebSmoke.dll "$index_root/asp-state"
index_run publish-aot "$OHECO_ROOT/bin/dotnet@$index_sdk" publish AotSmoke/AotSmoke.csproj -c Release -r openharmony-arm64 --disable-build-servers -o "$index_root/aot output"
index_run run-aot "$index_root/aot output/AotSmoke" "$index_root/aot-state"
[[ $(< "$index_root/run-aot.log") == *'dynamic code=False'* ]]
index_shutdown
index_run install-previous "$index_oo" install dotnet-sdk@10.0.401-ohos.1 --no-switch
index_run switch-previous "$index_oo" switch dotnet-sdk 10.0.401-ohos.1
index_run previous-runtimes dotnet --list-runtimes
[[ $(< "$index_root/previous-runtimes.log") != *'Microsoft.AspNetCore.App'* ]]
index_run switch-current "$index_oo" switch dotnet-sdk "$index_sdk"
index_run current-runtimes dotnet --list-runtimes
[[ $(< "$index_root/current-runtimes.log") == *'Microsoft.AspNetCore.App 10.0.12 '* ]]
index_run remove-previous "$index_oo" remove dotnet-sdk@10.0.401-ohos.1
index_run remove-sdk "$index_oo" remove "dotnet-sdk@$index_sdk"
index_run remove-aspnet "$index_oo" remove "aspnetcore-runtime@$index_asp"
for index_entry in dotnet dotnet@10.0.401-ohos.1 "dotnet@$index_sdk" aspnetcore-runtime "aspnetcore-runtime@$index_asp"; do
    [[ ! -e "$OHECO_ROOT/bin/$index_entry" && ! -L "$OHECO_ROOT/bin/$index_entry" ]]
done
[[ ! -d "$OHECO_ROOT/packages/dotnet-sdk/$index_sdk" ]]
[[ ! -d "$OHECO_ROOT/packages/aspnetcore-runtime/$index_asp" ]]
index_run removed-list "$index_oo" list
print 'PASS official index install, versioned commands, Web/AOT, switching and uninstall'
