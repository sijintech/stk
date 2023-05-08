const { build } = require("esbuild");
const { Generator } = require("npm-dts");
const { dependencies } = require("./package.json");

const entryFile = "src/index.ts";
const shared = {
  entryPoints: [entryFile],
  bundle: true,
  platform: "node",
  external: Object.keys(dependencies),
};

build({
  ...shared,
  outfile: "dist/index.js",
});

build({
  ...shared,
  outfile: "dist/index.esm.js",
  format: "esm",
});

new Generator({
  entry: "index.ts",
  output: "dist/index.d.ts",
}).generate();
