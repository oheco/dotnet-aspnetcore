#!/usr/bin/zsh
# Run on the real host against complete signed and relocated installation trees.
set -eu
(( $# == 3 )) || { print -u2 'Usage: accept-web.zsh sdk-root asp-runtime-root new-private-directory'; exit 2; }
accept_sdk=${1:A}
accept_runtime=${2:A}
accept_root=${3:A}
accept_sources=${0:A:h}/acceptance
[[ ! -e $accept_root ]]
[[ -x $accept_sdk/bin/dotnet && -x $accept_runtime/bin/aspnetcore-runtime ]]
command -v binary-sign-tool >/dev/null
command -v clang >/dev/null
mkdir -p "$accept_root/tmp" "$accept_root/cli" "$accept_root/nuget" "$accept_root/appdata" "$accept_root/data"
export DOTNET_CLI_HOME="$accept_root/cli" NUGET_PACKAGES="$accept_root/nuget"
export DOTNET_ROOT="$accept_sdk" DOTNET_ROOT_ARM64="$accept_sdk"
export DOTNET_OHOS_TMPDIR="$accept_root/tmp" TMPDIR="$accept_root/tmp"
export APPDATA="$accept_root/appdata" XDG_DATA_HOME="$accept_root/data"
export DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export HTTP_PROXY=${DOTNET_OHOS_PROXY:-socks5://172.16.105.2:10808}
export HTTPS_PROXY=$HTTP_PROXY NO_PROXY= no_proxy=
unset LD_LIBRARY_PATH
accept_pid=''
accept_cleanup() {
    if [[ -n $accept_pid ]]; then
        kill "$accept_pid" 2>/dev/null || true
        wait "$accept_pid" 2>/dev/null || true
    fi
    "$accept_sdk/bin/dotnet" build-server shutdown > "$accept_root/shutdown.log" 2>&1 || true
}
trap accept_cleanup EXIT
accept_run() {
    local accept_name=$1
    shift
    print -r -- "RUN $accept_name"
    if "$@" > "$accept_root/$accept_name.log" 2>&1; then
        print -r -- "PASS $accept_name"
    else
        local accept_rc=$?
        cat "$accept_root/$accept_name.log"
        return $accept_rc
    fi
}
cp -R "$accept_sources" "$accept_root/source with spaces"
cd "$accept_root/source with spaces"
accept_run sdk-info "$accept_sdk/bin/dotnet" --info
accept_run runtimes "$accept_sdk/bin/dotnet" --list-runtimes
[[ $("$accept_sdk/bin/dotnet" --version) == 10.0.401 ]]
[[ $(< "$accept_root/runtimes.log") == *'Microsoft.AspNetCore.App 10.0.12 '* ]]
for accept_name in WebSmoke GrpcSmoke Probe; do
    accept_run "build-$accept_name" "$accept_sdk/bin/dotnet" build "$accept_name/$accept_name.csproj" -c Release --disable-build-servers
done
accept_run web-jit "$accept_sdk/bin/dotnet" WebSmoke/bin/Release/net10.0/WebSmoke.dll "$accept_root/jit-state"
accept_run standalone-runtime "$accept_runtime/bin/aspnetcore-runtime" WebSmoke/bin/Release/net10.0/WebSmoke.dll "$accept_root/standalone-state"
accept_run grpc "$accept_sdk/bin/dotnet" GrpcSmoke/bin/Release/net10.0/GrpcSmoke.dll
accept_run web-r2r-publish "$accept_sdk/bin/dotnet" publish WebSmoke/WebSmoke.csproj -c Release -r openharmony-arm64 --self-contained true -p:PublishReadyToRun=true --disable-build-servers -o "$accept_root/r2r output"
accept_run web-r2r "$accept_root/r2r output/WebSmoke" "$accept_root/r2r-state"
accept_run aot-publish "$accept_sdk/bin/dotnet" publish AotSmoke/AotSmoke.csproj -c Release -r openharmony-arm64 --disable-build-servers -o "$accept_root/aot output"
accept_run aot "$accept_root/aot output/AotSmoke" "$accept_root/aot-state"
[[ $(< "$accept_root/aot.log") == *'dynamic code=False'* ]]

# Exercise templates and compiled/published static assets with a real HTTP client.
accept_probe="$accept_root/source with spaces/Probe/bin/Release/net10.0/Probe.dll"
for accept_template in web mvc webapp blazor webapi; do
    accept_project="$accept_root/template-$accept_template"
    accept_run "new-$accept_template" "$accept_sdk/bin/dotnet" new "$accept_template" --name TemplateApp --output "$accept_project" --no-restore
    accept_run "publish-$accept_template" "$accept_sdk/bin/dotnet" publish "$accept_project/TemplateApp.csproj" -c Release --disable-build-servers -o "$accept_project/published"
    (
        cd "$accept_project/published"
        exec "$accept_sdk/bin/dotnet" TemplateApp.dll --urls http://127.0.0.1:0
    ) > "$accept_root/serve-$accept_template.log" 2>&1 &
    accept_pid=$!
    accept_url=''
    for accept_retry in {1..100}; do
        for accept_line in "${(@f)$(< "$accept_root/serve-$accept_template.log")}"; do
            if [[ $accept_line == *'Now listening on: http://127.0.0.1:'* ]]; then
                accept_url="http://${accept_line##*http://}"
            fi
        done
        [[ -n $accept_url ]] && break
        kill -0 "$accept_pid" 2>/dev/null || { cat "$accept_root/serve-$accept_template.log"; exit 1; }
        sleep 0.2
    done
    [[ -n $accept_url ]]
    case $accept_template in
        web) accept_path=/; accept_text='Hello World!' ;;
        webapi) accept_path=/weatherforecast; accept_text='temperatureC' ;;
        *) accept_path=/; accept_text='html' ;;
    esac
    accept_run "http-$accept_template" "$accept_sdk/bin/dotnet" "$accept_probe" "$accept_url$accept_path" "$accept_text"
    if [[ $accept_template == blazor ]]; then
        accept_run blazor-framework-js "$accept_sdk/bin/dotnet" "$accept_probe" "$accept_url/_framework/blazor.web.js" 'Blazor'
    fi
    kill "$accept_pid"
    wait "$accept_pid" || true
    accept_pid=''
done

accept_run dev-certs-help "$accept_sdk/bin/dotnet" dev-certs https --help
accept_run secrets-init "$accept_sdk/bin/dotnet" user-secrets init --project "$accept_root/template-web/TemplateApp.csproj"
accept_run secrets-set "$accept_sdk/bin/dotnet" user-secrets set acceptance:value probe-value --project "$accept_root/template-web/TemplateApp.csproj"
accept_run secrets-list "$accept_sdk/bin/dotnet" user-secrets list --project "$accept_root/template-web/TemplateApp.csproj"
[[ $(< "$accept_root/secrets-list.log") == *'probe-value'* ]]
accept_run secrets-remove "$accept_sdk/bin/dotnet" user-secrets remove acceptance:value --project "$accept_root/template-web/TemplateApp.csproj"
accept_run jwts-help "$accept_sdk/bin/dotnet" user-jwts --help
if ! "$accept_sdk/bin/dotnet" user-jwts create --project "$accept_root/template-web/TemplateApp.csproj" --name oheco-acceptance --audience https://oheco-accept.invalid > "$accept_root/jwts-create.private" 2>&1; then
    print -u2 "JWT creation failed; see $accept_root/jwts-create.private"
    exit 1
fi
print 'PASS jwts-create'
accept_run jwts-list "$accept_sdk/bin/dotnet" user-jwts list --project "$accept_root/template-web/TemplateApp.csproj"
# The human-readable table wraps cells at the terminal width. Validate the
# unwrapped JSON privately; it includes the synthetic token, so do not publish it.
"$accept_sdk/bin/dotnet" user-jwts list --output json --project "$accept_root/template-web/TemplateApp.csproj" > "$accept_root/jwts-list.private"
[[ $(< "$accept_root/jwts-list.private") == *'"Audience": "https://oheco-accept.invalid"'* ]]
print 'PASS jwts-audience-json'
accept_run jwts-clear "$accept_sdk/bin/dotnet" user-jwts clear --force --project "$accept_root/template-web/TemplateApp.csproj"
accept_run jwts-empty "$accept_sdk/bin/dotnet" user-jwts list --output json --project "$accept_root/template-web/TemplateApp.csproj"
[[ $(< "$accept_root/jwts-empty.log") == '[]' ]]
rm -f "$accept_root/jwts-create.private" "$accept_root/jwts-list.private"
accept_run new-console "$accept_sdk/bin/dotnet" new console --name ConsoleProbe --output "$accept_root/console with spaces" --no-restore
cd "$accept_root/console with spaces"
for accept_revision in 1 2; do
    print -r -- "Console.WriteLine(\"console revision $accept_revision\");" > Program.cs
    accept_run "console-build-$accept_revision" "$accept_sdk/bin/dotnet" build -c Release --disable-build-servers
    accept_run "console-run-$accept_revision" ./bin/Release/net10.0/ConsoleProbe
    [[ $(< "$accept_root/console-run-$accept_revision.log") == "console revision $accept_revision" ]]
done
print 'PASS full ASP.NET Core native acceptance'
