import path from "path";
import { fileURLToPath } from "url";
import { rm, cp } from "fs/promises";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "../..");

async function buildAll() {
  const distDir = path.resolve(__dirname, "dist");
  await rm(distDir, { recursive: true, force: true });

  console.log("copying main app build to api-server dist...");
  await cp(path.resolve(rootDir, "dist/index.cjs"), path.resolve(distDir, "index.cjs"));
  await cp(path.resolve(rootDir, "dist/public"), path.resolve(distDir, "public"), { recursive: true });
  console.log("done");
}

buildAll().catch((err) => {
  console.error(err);
  process.exit(1);
});
