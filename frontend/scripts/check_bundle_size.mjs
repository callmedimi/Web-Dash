import fs from "fs";
import path from "path";
import zlib from "zlib";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DIST_ASSETS = path.resolve(__dirname, "../dist/assets");
const MAX_INITIAL_JS_GZIP_KB = 250;
const MAX_CHUNK_GZIP_KB = 150;
const MAX_CSS_GZIP_KB = 50;

if (!fs.existsSync(DIST_ASSETS)) {
  console.error(`Dist assets directory not found: ${DIST_ASSETS}`);
  process.exit(1);
}

const files = fs.readdirSync(DIST_ASSETS);
let failed = false;

console.log("=== Web-Dash Performance & Bundle Size Gate ===");
console.log(`Checking assets in ${DIST_ASSETS}\n`);

for (const file of files) {
  const filePath = path.join(DIST_ASSETS, file);
  const rawBytes = fs.readFileSync(filePath);
  const gzipBytes = zlib.gzipSync(rawBytes).length;

  const rawKb = (rawBytes.length / 1024).toFixed(1);
  const gzipKb = (gzipBytes / 1024).toFixed(1);
  const gzipKbNum = gzipBytes / 1024;

  let limit = MAX_CHUNK_GZIP_KB;
  let type = "chunk";

  if (file.startsWith("index-") && file.endsWith(".js")) {
    limit = MAX_INITIAL_JS_GZIP_KB;
    type = "initial-js";
  } else if (file.endsWith(".css")) {
    limit = MAX_CSS_GZIP_KB;
    type = "css";
  }

  const status = gzipKbNum <= limit ? "PASS" : "FAIL";
  if (status === "FAIL") failed = true;

  console.log(
    `[${status}] ${file.padEnd(28)} | ${type.padEnd(10)} | raw: ${rawKb.padStart(6)} KB | gzip: ${gzipKb.padStart(5)} KB (budget: ≤ ${limit} KB)`
  );
}

console.log("\n================================================");
if (failed) {
  console.error("FAILED: One or more bundle chunks exceeded size budgets!");
  process.exit(1);
} else {
  console.log("SUCCESS: All bundle artifacts are within strict performance budgets.");
  process.exit(0);
}
