#!/usr/bin/env bash
set -Eeuo pipefail
umask 022
root=${AURALIS_DEPLOY_ROOT:-/opt/auralis}
legacy=${AURALIS_LEGACY_ROOT:-/opt/sitechat}
bundle=$(realpath "${1:?Usage: deploy.sh release.tgz commit release-id}")
commit=${2:?Commit required}
release_id=${3:?Release ID required}
[[ "$commit" =~ ^[a-f0-9]{40}$ && "$release_id" =~ ^[a-f0-9]{40}-[0-9]+-[0-9]+$ ]] || exit 2
[[ "$release_id" == "$commit"-* && -L "$root/current" ]] || exit 2
exec 9>"$root/deploy.lock"
flock -n 9 || { echo 'Another deployment holds the server lock.' >&2; exit 1; }
previous=$(readlink -f "$root/current")
release="$root/releases/$release_id"
[[ "$previous" == "$root/releases/"* && ! -e "$release" ]] || exit 2
[[ -f "$legacy/backend/.env" && -d "$legacy/backend/data" && -d "$legacy/backend/logs" ]] || exit 2
systemctl is-active --quiet mongod nginx
mongosh --quiet --eval 'if (db.adminCommand({ping:1}).ok !== 1) quit(1)' >/dev/null
[[ $(systemctl show sitechat -p WorkingDirectory --value) == "$root/current/backend" ]] || {
    echo 'Run deploy/setup-ec2.sh before enabling deployments.' >&2; exit 1;
}
[[ $(systemctl show auralis-web -p WorkingDirectory --value) == "$root/current/web/.next/standalone" ]] || {
    echo 'The web service is not configured to use the release symlink.' >&2; exit 1;
}
[[ $(tar -xOf "$bundle" COMMIT) == "$commit" ]] || { echo 'Artifact commit mismatch.' >&2; exit 1; }
mkdir "$release"
tar -xzf "$bundle" -C "$release" --no-same-owner --no-same-permissions
for path in backend/.env backend/data backend/logs backend/.venv web/.next/standalone/.next/cache; do
    [[ ! -e "$release/$path" && ! -L "$release/$path" ]] || { echo "Forbidden artifact path: $path" >&2; exit 1; }
done
ln -s "$legacy/backend/.env" "$release/backend/.env"
ln -s "$legacy/backend/data" "$release/backend/data"
ln -s "$legacy/backend/logs" "$release/backend/logs"
ln -s "$root/shared/web-cache" "$release/web/.next/standalone/.next/cache"
python3 -m venv "$release/backend/.venv"
"$release/backend/.venv/bin/python" -m pip install --disable-pip-version-check -r "$release/backend/requirements.lock.txt"
"$release/backend/.venv/bin/python" -m pip check
changed=false
switch_to() {
    ln -s "$1" "$root/.current-$release_id"
    mv -Tf "$root/.current-$release_id" "$root/current"
}
service_action() {
    sudo -n /usr/bin/systemctl "$1" sitechat
    sudo -n /usr/bin/systemctl "$1" auralis-web
}
rollback() {
    status=$?
    trap - EXIT
    if (( status != 0 )) && [[ "$changed" == true ]]; then
        echo "Deployment $release_id failed; restoring code from $previous." >&2
        service_action stop || true
        switch_to "$previous"
        service_action start || true
        HEALTH_TIMEOUT=600 bash "$release/deploy/healthcheck.sh" || echo 'Rollback health check failed; operator action required.' >&2
    fi
    exit "$status"
}
trap rollback EXIT
echo "Switching code from $previous to $release (commit $commit)."
# Set before stopping either unit so partial stop failures also restart the old release.
changed=true
service_action stop
switch_to "$release"
service_action start
bash "$release/deploy/healthcheck.sh" "$commit"
sudo -n /usr/bin/systemctl restart auralis-smoke
printf '%s %s\n' "$(date -u +%FT%TZ)" "$release_id" >> "$root/deployments.log"
echo "Deployed $commit successfully. Data and secrets remain at $legacy/backend."
