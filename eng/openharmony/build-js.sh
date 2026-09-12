#!/usr/bin/env bash
# Build only the browser resources used by the ASP.NET shared framework/SDK.
set -euo pipefail
port_source=${1:?Usage: build-js.sh source-directory verified-npm-cache new-log-file}
port_cache=${2:?Missing verified npm cache}
port_log=${3:?Missing new log path}
[[ ! -e "$port_log" ]] || { echo 'Use a new log file' >&2; exit 2; }
[[ $(node --version) == v24.15.0 ]] || { echo 'Use pinned Node.js 24.15.0' >&2; exit 2; }
export npm_config_cache=$port_cache
export npm_config_offline=true
export npm_config_audit=false
export npm_config_fund=false
export npm_config_update_notifier=false
export ContinuousIntegrationBuild=true
cd -- "$port_source"
exec > "$port_log" 2>&1
npm ci --offline --ignore-scripts --registry=https://registry.npmjs.org --include-workspace-root \
    --workspace=./src/SignalR/clients/ts --workspace=@microsoft/functionaltests --workspace=@microsoft/signalr --workspace=@microsoft/signalr-protocol-msgpack \
    --workspace=@microsoft/dotnet-js-interop --workspace=@microsoft/microsoft.aspnetcore.components.web.js

# Upstream npm version may re-resolve dependencies. Set only the same workspace
# package versions/dependency strings after the locked install, without invoking
# the installer again. These are generated build inputs in this checkout.
python3 - <<'PY'
import json
from pathlib import Path
packages = []
for workspace in json.loads(Path('package.json').read_text())['workspaces']:
    path = Path(workspace) / 'package.json'
    item = json.loads(path.read_text())
    if not item.get('private'):
        packages.append((path, item))
names = {item['name'] for _, item in packages}
for path, item in packages:
    item['version'] = '10.0.12'
    for name in item.get('dependencies', {}):
        if name in names:
            item['dependencies'][name] = '>=10.0.12'
    path.write_text(json.dumps(item, indent=2) + '\n')
PY
npm run build --workspace=@microsoft/signalr --workspace=@microsoft/signalr-protocol-msgpack \
    --workspace=@microsoft/dotnet-js-interop --workspace=@microsoft/microsoft.aspnetcore.components.web.js
for port_asset in blazor.server.js blazor.web.js blazor.webassembly.js; do
    [[ -s "src/Components/Web.JS/dist/Release/$port_asset" ]]
done
