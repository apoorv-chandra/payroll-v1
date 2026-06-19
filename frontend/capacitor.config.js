/**
 * Capacitor configuration — wraps the React PWA into a native Android app.
 *
 *  • `webDir` points at CRA's production build output.
 *  • `appId` follows reverse-DNS convention (also the Java package).
 *  • `androidScheme: "https"` is required so cookies + service-workers behave
 *    identically to the production web app.
 *
 * Build steps (manual — run on a machine with Android SDK + JDK 17 installed):
 *
 *   1. cd /app/frontend
 *   2. yarn build                      # produces /app/frontend/build/
 *   3. npx cap sync android            # copies build → android/app/src/main/assets/public
 *   4. npx cap open android            # launches Android Studio (optional)
 *   5. cd android && ./gradlew assembleDebug
 *      → APK at android/app/build/outputs/apk/debug/app-debug.apk
 *
 * For release / Play Store:
 *   ./gradlew bundleRelease  → app-release.aab
 */
const config = {
  appId: "com.norratech.payrollstudents",
  appName: "Payroll & Students",
  webDir: "build",
  bundledWebRuntime: false,
  server: {
    // androidScheme=https aligns the in-app URL scheme with the production
    // backend so Bearer tokens / cookies / SW work identically.
    androidScheme: "https",
    // Allow loading the backend from the production URL on the device.
    // Use cleartext only in dev — release builds should hit HTTPS only.
    cleartext: false,
  },
  android: {
    allowMixedContent: false,
    // Splash screen — auto-hidden once React mounts.
    backgroundColor: "#0F172A",
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1500,
      backgroundColor: "#0F172A",
      androidScaleType: "CENTER_CROP",
      showSpinner: false,
    },
    Geolocation: {
      // Default to high accuracy on Android — we use it for attendance pins.
      enableHighAccuracy: true,
    },
  },
};

module.exports = config;
