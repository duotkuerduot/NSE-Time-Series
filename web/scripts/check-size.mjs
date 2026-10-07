// Initial JavaScript budget: 150 KB gzipped (NFR-04).
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const BUDGET = 150 * 1024;
// fileURLToPath, not URL.pathname: the latter keeps %20 for spaces and breaks on Windows.
const dir = fileURLToPath(new URL("../dist/assets/", import.meta.url));
const files = (await readdir(dir)).filter((f) => f.endsWith(".js"));
let total = 0;
for (const f of files) total += gzipSync(await readFile(join(dir, f))).length;
const kb = (total / 1024).toFixed(1);
if (total > BUDGET) {
  console.error(`JavaScript is ${kb} KB gzipped; budget is ${BUDGET / 1024} KB`);
  process.exit(1);
}
console.log(`JavaScript is ${kb} KB gzipped (budget ${BUDGET / 1024} KB)`);
