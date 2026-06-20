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

cd "$ROOT"

echo "==> [1/4] Building React PWA"
yarn build

echo "==> [2/4] Capacitor sync"
npx cap sync android

echo "==> [3/4] Gradle assembleDebug"
cd "$ROOT/android"
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew --no-daemon assembleDebug \
    -Pandroid.aapt2FromMavenOverride="$APK_OVERRIDE"

echo "==> [4/4] Stashing APK"
mkdir -p "$DIST"
cp "$APK_OUT" "$DIST/payroll-debug.apk"
sha256sum "$DIST/payroll-debug.apk"
ls -lh "$DIST/payroll-debug.apk"

echo
echo "Done. APK is at:  $DIST/payroll-debug.apk"
