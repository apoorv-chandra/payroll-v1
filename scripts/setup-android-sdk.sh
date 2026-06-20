#!/usr/bin/env bash
# One-time setup for the Android build toolchain inside this container.
#
# The hard part: this container is aarch64 (ARM64) but Google ships only
# x86_64 Linux build-tools / platform-tools. We work around that by:
#   • installing OpenJDK 17 + a manual JDK 21 (Capacitor 6 plugins need 21)
#   • installing qemu-x86_64-static + amd64 libc / libstdc++
#   • renaming every x86_64 ELF binary under build-tools / platform-tools to
#     `<name>.x86_64` and dropping a shell wrapper that exec's qemu.
#
# Run once after a fresh checkout; subsequent APK builds use scripts/build-android-apk.sh
#
# Disk: ~700 MB (SDK 460 MB + JDK 21 200 MB).
#
set -euo pipefail

# 1. JDK 17 (for Gradle) and JDK 21 (for Capacitor plugins).
echo "==> Installing OpenJDK 17 + tooling via apt"
DEBIAN_FRONTEND=noninteractive apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    openjdk-17-jdk-headless unzip wget file \
    qemu-user-static binfmt-support

# 2. Enable amd64 multiarch + libc so qemu-x86_64-static can resolve the linker.
echo "==> Enabling amd64 multiarch for qemu"
dpkg --add-architecture amd64
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    libc6:amd64 zlib1g:amd64 libstdc++6:amd64

# 3. JDK 21 (no Debian 12 apt package yet) — manual install for aarch64.
echo "==> Installing JDK 21 (aarch64) into /opt/jdks"
mkdir -p /opt/jdks
if [ ! -d /opt/jdks/jdk-21-aarch64 ]; then
    cd /tmp
    wget -q "https://download.java.net/java/GA/jdk21.0.2/f2283984656d49d69e91c558476027ac/13/GPL/openjdk-21.0.2_linux-aarch64_bin.tar.gz" -O jdk21.tar.gz
    tar -xzf jdk21.tar.gz -C /opt/jdks
    mv /opt/jdks/jdk-21.0.2 /opt/jdks/jdk-21-aarch64
fi
/opt/jdks/jdk-21-aarch64/bin/java -version

# 4. Android command-line tools.
echo "==> Installing Android command-line tools"
ANDROID_HOME=/app/android-sdk
mkdir -p "$ANDROID_HOME/cmdline-tools"
if [ ! -d "$ANDROID_HOME/cmdline-tools/latest" ]; then
    cd /tmp
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O cmdtools.zip
    unzip -q -o cmdtools.zip -d "$ANDROID_HOME/cmdline-tools"
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
fi

# 5. Accept licenses + install SDK packages.
echo "==> Accepting SDK licenses + installing platform 35 + build-tools 35"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-arm64
yes | sdkmanager --licenses > /dev/null
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"

# 6. Wrap every x86_64 ELF binary under build-tools + platform-tools so it
# runs transparently under qemu-x86_64-static.
echo "==> Wrapping x86_64 SDK binaries for qemu transparent emulation"
for dir in "$ANDROID_HOME/build-tools/35.0.0" "$ANDROID_HOME/platform-tools"; do
    for f in "$dir"/*; do
        [ -f "$f" ] || continue
        [ -x "$f" ] || continue
        case "$f" in *.x86_64|*.sh|*.txt|*.so*) continue;; esac
        # Skip if not ELF
        head -c4 "$f" 2>/dev/null | grep -q $'\x7fELF' || continue
        # Skip if already wrapped (file content starts with #!/bin/sh would
        # not pass the ELF check anyway, so this is fine).
        if file "$f" | grep -q x86-64; then
            mv "$f" "$f.x86_64"
            cat > "$f" <<INNER
#!/bin/sh
exec qemu-x86_64-static "$f.x86_64" "\$@"
INNER
            chmod +x "$f"
        fi
    done
done

echo
echo "Done. Now run:  scripts/build-android-apk.sh"
