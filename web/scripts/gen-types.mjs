// Generates TypeScript types from the API contract's JSON Schema (ENGINEERING.md 22.1).
// `--check` fails when the committed types are out of date, so CI catches contract drift.
import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const schemaDir = resolve(here, "../../contracts/api/v1");
const outDir = resolve(here, "../src/api/types");
const check = process.argv.includes("--check");

const banner = "// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.\n";
const files = (await readdir(schemaDir)).filter((f) => f.endsWith(".schema.json")).sort();
let stale = 0;
await mkdir(outDir, { recursive: true });
for (const file of files) {
  const schema = JSON.parse(await readFile(join(schemaDir, file), "utf8"));
  const ts = await compile(schema, schema.title, {
    bannerComment: banner,
    additionalProperties: false,
    format: false,
    unreachableDefinitions: false,
  });
  const target = join(outDir, file.replace(".schema.json", ".gen.ts"));
  const current = await readFile(target, "utf8").catch(() => "");
  if (current === ts) continue;
  if (check) {
    console.error(`stale: ${target}`);
    stale += 1;
  } else {
    await writeFile(target, ts);
    console.log(`wrote ${target}`);
  }
}
if (stale) {
  console.error("Run `pnpm gen:types` and commit the result.");
  process.exit(1);
}
