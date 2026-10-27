#!/usr/bin/env bash
# Run once as root after reviewing the EC2 audit and backing up current data.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo bash deploy/setup-ec2.sh' >&2; exit 1; }
legacy=/opt/sitechat
root=/opt/auralis
[[ ! -e "$root/current" && ! -L "$root/current" ]] || { echo 'Already initialized; refusing to overwrite current.' >&2; exit 1; }
[[ -f "$legacy/backend/.env" && -x "$legacy/backend/.venv/bin/python" && -f "$legacy/web/.next/standalone/server.js" && -f "$legacy/widget/dist/chatbot.js" ]] || exit 1
systemctl is-active --quiet mongod sitechat auralis-web nginx
mongosh --quiet --eval 'if (db.adminCommand({ping:1}).ok !== 1) quit(1)' >/dev/null
for unit in sitechat auralis-web; do
    [[ $(systemctl show "$unit" -p User --value) == ubuntu ]] || exit 1
    [[ ! -e "/etc/systemd/system/$unit.service.d/ci-cd.conf" ]] || exit 1
done
# Relative application storage must resolve into the existing data directory.
cd "$legacy/backend"
sudo -u ubuntu "$legacy/backend/.venv/bin/python" - <<'PY'
from pathlib import Path
from app.config import settings
base = Path('/opt/sitechat/backend/data').resolve()
for name in ['CHROMA_PERSIST_DIR', 'FAISS_INDEX_PATH', 'LOCAL_STORAGE_PATH']:
    path = Path(getattr(settings, name)).resolve()
    if not path.is_relative_to(base):
        raise SystemExit(f'{name} is outside backend/data; adapt the shared links before setup')
PY
id auralis-deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash auralis-deploy
install -d -m 755 -o auralis-deploy -g auralis-deploy "$root" "$root/releases" "$root/releases/baseline"
install -d -m 755 -o ubuntu -g ubuntu "$root/shared" "$root/shared/web-cache"
install -d -m 755 -o root -g root /var/lib/auralis-deploy /var/lib/auralis-deploy/incoming
for component in backend web widget; do
    ln -s "$legacy/$component" "$root/releases/baseline/$component"
done
git -c safe.directory="$legacy" -C "$legacy" rev-parse HEAD > "$root/releases/baseline/COMMIT"
ln -s "$root/releases/baseline" "$root/current"
install -d /etc/systemd/system/sitechat.service.d /etc/systemd/system/auralis-web.service.d
cat > /etc/systemd/system/sitechat.service.d/ci-cd.conf <<'UNIT'
[Service]
WorkingDirectory=/opt/auralis/current/backend
ExecStart=
ExecStart=/opt/auralis/current/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
TimeoutStartSec=600
UNIT
cat > /etc/systemd/system/auralis-web.service.d/ci-cd.conf <<'UNIT'
[Service]
WorkingDirectory=/opt/auralis/current/web/.next/standalone
ExecStart=
ExecStart=/usr/bin/node /opt/auralis/current/web/.next/standalone/server.js
Environment=NODE_ENV=production
Environment=HOSTNAME=127.0.0.1
Environment=PORT=3000
UNIT
cat > /etc/systemd/system/auralis-smoke.service <<'UNIT'
[Unit]
Description=Auralis bounded LLM inference check
After=sitechat.service
[Service]
Type=oneshot
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/auralis/current/backend
Environment=PYTHONPATH=/opt/auralis/current/backend
ExecStart=/opt/auralis/current/backend/.venv/bin/python /opt/auralis/current/deploy/check_llm.py
TimeoutStartSec=90
UNIT
sudoers=$(mktemp)
trap 'rm -f "$sudoers"' EXIT
cat > "$sudoers" <<'SUDOERS'
auralis-deploy ALL=(root) NOPASSWD: /usr/bin/systemctl stop sitechat, /usr/bin/systemctl start sitechat, /usr/bin/systemctl stop auralis-web, /usr/bin/systemctl start auralis-web, /usr/bin/systemctl restart auralis-smoke
SUDOERS
visudo -cf "$sudoers"
install -m 440 "$sudoers" /etc/sudoers.d/auralis-deploy
systemctl daemon-reload
echo 'Initialized baseline and systemd drop-ins. Running services have not been restarted.'
echo 'Configure AWS OIDC + SSM using deploy/aws.yaml; see docs/CI_CD_VI.md.'
