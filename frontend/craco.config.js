/**
 * CRACO config — overrides Create-React-App's webpack config without ejecting.
 *
 * Why we need this
 * ----------------
 * `face-api.js` is an isomorphic library (works in both Node and browser).
 * Its env detection module conditionally `require('fs')` for the Node path.
 * Webpack 5 stopped polyfilling Node core modules, so even though the code
 * is dead-eliminated for browser bundles, webpack still raises a noisy
 * "Module not found: Can't resolve 'fs'" warning during the build.
 *
 * Telling webpack to resolve `fs` (and friends) to `false` makes it emit an
 * empty shim and the warning goes away. The browser bundle stays unchanged.
 */
module.exports = {
  webpack: {
    configure: (webpackConfig) => {
      webpackConfig.resolve = webpackConfig.resolve || {};
      webpackConfig.resolve.fallback = {
        ...(webpackConfig.resolve.fallback || {}),
        fs: false,
        path: false,
        crypto: false,
        os: false,
      };

      // Silence the "Failed to parse source map" noise from dependencies that
      // ship a .js.map referencing missing .ts sources (face-api.js, etc.).
      // GENERATE_SOURCEMAP=false in .env already handles this for prod, but
      // CI logs sometimes still surface it — belt-and-braces.
      webpackConfig.ignoreWarnings = [
        ...(webpackConfig.ignoreWarnings || []),
        /Failed to parse source map/,
      ];

      return webpackConfig;
    },
  },
};
