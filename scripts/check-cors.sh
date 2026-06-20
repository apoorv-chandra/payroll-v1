#!/usr/bin/env bash
# Quick CORS sanity check against the production Render backend.
# Use after updating CORS_ORIGINS on Render to confirm every origin you care
# about gets a matching `Access-Control-Allow-Origin` header back.
#
# Usage:   bash scripts/check-cors.sh
#          bash scripts/check-cors.sh https://other-host.onrender.com
set -euo pipefail
URL=${1:-https://payroll-api-8x2w.onrender.com}
EP=/api/auth/captcha

ORIGINS=(
    "https://payroll-v1-ceq.pages.dev"   # Cloudflare web
    "https://localhost"                  # Capacitor Android
    "capacitor://localhost"              # Capacitor iOS
)

printf "%-30s  %s\n" "Origin" "Access-Control-Allow-Origin"
printf "%-30s  %s\n" "------" "---------------------------"
for o in "${ORIGINS[@]}"; do
    hdr=$(curl -s -D - "$URL$EP" -H "Origin: $o" -o /dev/null \
          | grep -i '^access-control-allow-origin:' | cut -d: -f2- \
          | tr -d '\r' | xargs)
    if [ -z "$hdr" ]; then
        printf "%-30s  %s\n" "$o" "(missing) ✗"
    else
        printf "%-30s  %s ✓\n" "$o" "$hdr"
    fi
done
