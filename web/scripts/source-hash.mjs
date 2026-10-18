// The SHA-256 written to src/nsefc/web_dist/.source-hash after every build.
// It must match `uv run nsefc dev web-hash` (src/nsefc/devtools): web/src/** sorted by POSIX path,
// then the build inputs; each file contributes its path, a NUL, its bytes with CRLF read as LF,
// and a NUL. CI recomputes it in Python and fails if the committed build is stale.
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";

const INPUTS = ["web/index.html", "web/package.json", "web/pnpm-lock.yaml", "web/vite.config.ts"];

function walk(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return walk(path);
    return entry.isFile() ? [path] : [];
  });
}

export function sourceHash(repoRoot) {
  const sources = walk(join(repoRoot, "web", "src"))
    .map((path) => relative(repoRoot, path).split(sep).join("/"))
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const files = [...sources, ...INPUTS.filter((name) => existsSync(join(repoRoot, ...name.split("/"))))];
  const digest = createHash("sha256");
  for (const name of files) {
    digest.update(Buffer.from(`${name}\0`, "utf8"));
    const bytes = readFileSync(join(repoRoot, ...name.split("/")));
    digest.update(Buffer.from(bytes.toString("latin1").replaceAll("\r\n", "\n"), "latin1"));
    digest.update(Buffer.from([0]));
  }
  return digest.digest("hex");
}
