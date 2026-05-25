// craco.config.js
const path = require("path");
require("dotenv").config();

const config = {
  webpack: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
    cache: false,
    configure: (webpackConfig) => {
      webpackConfig.plugins = webpackConfig.plugins.filter(
        (p) =>
          p.constructor?.name !== "ForkTsCheckerWebpackPlugin" &&
          p.constructor?.name !== "ESLintWebpackPlugin"
      );
      webpackConfig.module.rules = webpackConfig.module.rules.map((rule) => {
        if (rule.use) {
          rule.use = rule.use.filter(
            (u) => !u.loader || !u.loader.includes("eslint-loader")
          );
        }
        return rule;
      });
      return webpackConfig;
    },
  },
  devServer: {
    hot: true,
    liveReload: true,
  },
  jest: {
    configure: {
      moduleNameMapper: {
        "^@/(.*)$": "<rootDir>/src/$1",
        "\\.(css|less|scss|sass)$": "identity-obj-proxy",
      },
    },
  },
};

module.exports = config;
