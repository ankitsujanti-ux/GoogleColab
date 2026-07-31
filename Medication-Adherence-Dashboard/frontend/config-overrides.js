// config-overrides.js for react-app-rewired
// This adds Node.js polyfills for webpack 5

module.exports = function override(config, env) {
  config.resolve.fallback = {
    ...config.resolve.fallback,
    "buffer": require.resolve("buffer/"),
    "stream": require.resolve("stream-browserify"),
    "assert": require.resolve("assert/"),
  };
  
  return config;
};
