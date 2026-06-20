#!/usr/bin/env bash
# Build the debug APK end-to-end inside this container.
#
# What this does
#   1. Re-uses the cached Android SDK at /app/android-sdk (if missing, run
#      scripts/setup-android-sdk.sh first).
#   2. Builds the React PWA (`yarn build`).
#   3. Syncs the build into the Capacitor android/ project.
#   4. Calls `./gradlew assembleDebug` with an aapt2 override (the SDK is
#      x86_64-only, so we run aapt2 through qemu-x86_64-static — see
#      scripts/setup-android-sdk.sh for how those wrappers were created).
#   5. Copies the APK to /app/dist/payroll-debug.apk for easy pickup.
#
# Output
#   /app/frontend/android/app/build/outputs/apk/debug/app-debug.apk
#   /app/dist/payroll-debug.apk           (convenience copy + sha256)
#
set -euo pipefail

export JAVA_HOME=/opt/jdks/jdk-21-aarch64
export ANDROID_HOME=/app/android-sdk
export ANDROID_SDK_ROOT=/app/android-sdk
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

ROOT=/app/frontend
APK_OVERRIDE=/app/android-sdk/build-tools/35.0.0/aapt2
DIST=/app/dist
APK_OUT="$ROOT/android/app/build/outputs/apk/debug/app-debug.apk"

# ----- Sanity: production env file must exist with a sensible backend URL ---
ENV_PROD="$ROOT/.env.production"
if [ ! -f "$ENV_PROD" ]; then
    echo "ERR: $ENV_PROD not found." >&2
    echo "     Copy frontend/.env.example and set REACT_APP_BACKEND_URL." >&2
    exit 1
fi
BACKEND_URL=$(grep -E "^REACT_APP_BACKEND_URL=" "$ENV_PROD" | head -1 | cut -d= -f2-)
if [ -z "$BACKEND_URL" ]; then
    echo "ERR: REACT_APP_BACKEND_URL is empty in $ENV_PROD." >&2
    exit 1
fi
case "$BACKEND_URL" in
    *localhost*|*preview.emergentagent.com*|*ngrok*)
        echo "WARN: APK is about to be built against a NON-PRODUCTION URL:" >&2
        echo "      $BACKEND_URL" >&2
        echo "      Anyone installing this APK will hit a dev backend." >&2
        echo "      Press Ctrl-C in 5s if that's wrong…" >&2
        sleep 5
        ;;
esac

cd "$ROOT"

echo "==> [1/4] React PWA build  (REACT_APP_BACKEND_URL=$BACKEND_URL)"
yarn build

echo "==> [2/4] Capacitor sync"
npx cap sync android

echo "==> [3/4] Gradle assembleDebug"
cd "$ROOT/android"
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew --no-daemon assembleDebug \
    -Pandroid.aapt2FromMavenOverride="$APK_OVERRIDE"

echo "==> [4/4] Stashing APK + verifying baked URL"
mkdir -p "$DIST"
cp "$APK_OUT" "$DIST/payroll-debug.apk"
sha256sum "$DIST/payroll-debug.apk"
ls -lh "$DIST/payroll-debug.apk"

# Confirm the URL inside the bundled JS matches what we expected.
TMP=$(mktemp -d)
unzip -q -o "$DIST/payroll-debug.apk" "assets/public/static/js/main.*.js" -d "$TMP"
if grep -F "$BACKEND_URL" "$TMP"/assets/public/static/js/main.*.js > /dev/null 2>&1; then
    echo "OK — APK bundle calls $BACKEND_URL"
else
    echo "ERR — expected URL $BACKEND_URL not found in APK bundle!" >&2
    grep -ohE 'https://[a-z0-9.-]+\.(onrender|emergentagent|pages\.dev|cloudflare)\.[a-z]+' "$TMP"/assets/public/static/js/main.*.js | sort -u | sed 's/^/      saw: /' >&2
    rm -rf "$TMP"
    exit 1
fi
rm -rf "$TMP"

echo
echo "Done. APK is at:  $DIST/payroll-debug.apk"
