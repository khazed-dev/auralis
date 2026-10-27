#!/usr/bin/env bash
# Exercise deployment and rollback with mocked services; never contacts the VPS.
set -euo pipefail
source_dir=$(cd "$(dirname "$0")" && pwd)
temp=$(mktemp -d)
trap 'rm -rf "$temp"' EXIT
real_python=$(command -v python3 || command -v python)
export REAL_PYTHON="$real_python"
mkdir "$temp/bin"
cat > "$temp/bin/systemctl" <<'MOCK'
#!/usr/bin/env bash
if [[ "$1" == show ]]; then
    if [[ "$2" == sitechat ]]; then echo "$AURALIS_DEPLOY_ROOT/current/backend";
    else echo "$AURALIS_DEPLOY_ROOT/current/web/.next/standalone"; fi
fi
MOCK
cat > "$temp/bin/mongosh" <<'MOCK'
#!/usr/bin/env bash
[[ "${FAIL_MONGO:-false}" != true ]]
MOCK
cat > "$temp/bin/sudo" <<'MOCK'
#!/usr/bin/env bash
echo "$*" >> "$ACTION_LOG"
if [[ "$*" == *'restart auralis-smoke' && "${FAIL_SMOKE:-false}" == true ]]; then exit 1; fi
MOCK
cat > "$temp/bin/curl" <<'MOCK'
#!/usr/bin/env bash
if [[ "$*" == *'/api/ready'* ]]; then
    state=ready
    [[ "${FAIL_READY:-false}" != true ]] || state=not_ready
    printf '{"status":"%s","commit":"%s"}\n' "$state" "$EXPECTED_COMMIT"
elif [[ "$*" == *'%{http_code}'* ]]; then
    printf 200
fi
MOCK
cat > "$temp/bin/python3" <<'MOCK'
#!/usr/bin/env bash
if [[ "${1:-}" == -m && "${2:-}" == venv ]]; then
    mkdir -p "$3/bin"
    printf '#!/usr/bin/env bash\n[[ "${FAIL_PIP:-false}" != true ]]\n' > "$3/bin/python"
    chmod +x "$3/bin/python"
else
    exec "$REAL_PYTHON" "$@"
fi
MOCK
chmod +x "$temp/bin/"*
export PATH="$temp/bin:$PATH"
export EXPECTED_COMMIT=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export HEALTH_TIMEOUT=1
for scenario in success smoke_failure readiness_failure pip_failure mongo_failure; do
    base="$temp/$scenario"
    export AURALIS_DEPLOY_ROOT="$base/root" AURALIS_LEGACY_ROOT="$base/legacy" ACTION_LOG="$base/actions.log"
    export FAIL_SMOKE=false FAIL_PIP=false FAIL_MONGO=false FAIL_READY=false
    case "$scenario" in
        smoke_failure) export FAIL_SMOKE=true ;;
        readiness_failure) export FAIL_READY=true ;;
        pip_failure) export FAIL_PIP=true ;;
        mongo_failure) export FAIL_MONGO=true ;;
    esac
    mkdir -p "$base/root/releases/baseline" "$base/root/shared/web-cache" "$base/legacy/backend/data" "$base/legacy/backend/logs" "$base/artifact/backend/app" "$base/artifact/web/.next/standalone/.next" "$base/artifact/deploy"
    echo secret-sentinel > "$base/legacy/backend/.env"
    echo data-sentinel > "$base/legacy/backend/data/index.pkl"
    ln -s "$base/root/releases/baseline" "$base/root/current"
    printf '%s\n' "$EXPECTED_COMMIT" > "$base/artifact/COMMIT"
    touch "$base/artifact/backend/requirements.lock.txt"
    cp "$source_dir/healthcheck.sh" "$base/artifact/deploy/healthcheck.sh"
    tar -czf "$base/release.tgz" -C "$base/artifact" COMMIT backend web deploy
    status=0
    bash "$source_dir/deploy.sh" "$base/release.tgz" "$EXPECTED_COMMIT" "$EXPECTED_COMMIT-1-1" > "$base/output.log" 2>&1 || status=$?
    if [[ "$scenario" == success ]]; then
        [[ $status == 0 && $(readlink -f "$base/root/current") == "$base/root/releases/$EXPECTED_COMMIT-1-1" ]]
        [[ -L "$base/root/current/backend/data" && -f "$base/root/deployments.log" ]]
    else
        [[ $status != 0 && $(readlink -f "$base/root/current") == "$base/root/releases/baseline" ]]
        if [[ "$scenario" == smoke_failure || "$scenario" == readiness_failure ]]; then
            grep -q 'restoring code' "$base/output.log"
            [[ $(grep -c 'start sitechat' "$ACTION_LOG") == 2 ]]
        else
            [[ ! -e "$ACTION_LOG" ]]
        fi
    fi
    [[ $(cat "$base/legacy/backend/.env") == secret-sentinel ]]
    [[ $(cat "$base/legacy/backend/data/index.pkl") == data-sentinel ]]
    echo "PASS: $scenario preserves data and secrets"
done
