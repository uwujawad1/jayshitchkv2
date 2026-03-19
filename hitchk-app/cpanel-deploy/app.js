const path = require("path");

process.env.NODE_ENV = "production";

if (typeof PhusionPassenger !== "undefined") {
  PhusionPassenger.configure({ autoInstall: false });
}

require("./dist/index.cjs");
