#!/usr/bin/env bash
set -euo pipefail
expected_commit=${1:-}
timeout=${HEALTH_TIMEOUT:-600}
deadline=$((SECONDS + timeout))
while (( SECONDS < deadline )); do
    if systemctl is-active --quiet mongod sitechat auralis-web nginx &&
        curl -fsS --max-time 5 http://127.0.0.1:3000/login -o /dev/null &&
        curl -fsS --max-time 5 http://127.0.0.1:8000/chatbot.js -o /dev/null; then
        if [[ -z "$expected_commit" ]] || curl -fsS --max-time 5 http://127.0.0.1:8000/api/ready |
            python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(not(d["status"]=="ready" and d["commit"]==sys.argv[1]))' "$expected_commit"; then
            break
        fi
    fi
    sleep 5
done
(( SECONDS < deadline )) || { echo 'Readiness timed out.' >&2; exit 1; }
mongosh --quiet --eval 'if (db.adminCommand({ping:1}).ok !== 1) quit(1)' >/dev/null
for path in / /login /chatbot.js; do
    code=$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' "${PUBLIC_URL:-https://auralisai.duckdns.org}$path")
    [[ "$code" == 200 ]] || { echo "Public check failed: $path HTTP $code" >&2; exit 1; }
done
echo 'MongoDB, application readiness, web, widget and HTTPS checks passed.'
