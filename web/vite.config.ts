import { readFile, stat, writeFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import react from "@vitejs/plugin-react";
import type { Connect, Plugin } from "vite";
import { defineConfig } from "vitest/config";
import { sourceHash } from "./scripts/source-hash.mjs";

const REPO = resolve(import.meta.dirname, "..");
const FIXTURES = resolve(REPO, "contracts/api/v1/fixtures");
// The built app ships inside the Python package, so running the tool needs no Node.js.
const OUT_DIR = resolve(REPO, "src/nsefc/web_dist");

// Serves the contract fixtures at /api/v1 in `vite` and `vite preview`, so every page renders
// without running the pipeline. The real app is served by `nsefc serve`.
function serveFixtures(): Plugin {
  const middleware: Connect.NextHandleFunction = async (req, res, next) => {
    const url = (req.url ?? "").split("?")[0] ?? "";
    if (!url.startsWith("/api/v1/")) return next();
    const file = resolve(FIXTURES, `.${url.slice("/api/v1".length)}`);
    if (!file.startsWith(FIXTURES + sep)) return next();
    try {
      if (!(await stat(file)).isFile()) return next();
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(await readFile(file));
    } catch {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: url } }));
    }
  };
  return {
    name: "nsefc-fixtures",
    configureServer: (server) => void server.middlewares.use(middleware),
    configurePreviewServer: (server) => void server.middlewares.use(middleware),
  };
}

// Records which sources the build came from; `uv run nsefc dev web-hash --check` compares it.
function recordSourceHash(): Plugin {
  return {
    name: "nsefc-source-hash",
    apply: "build",
    closeBundle: async () => {
      await writeFile(resolve(OUT_DIR, ".source-hash"), `${sourceHash(REPO)}\n`, "utf8");
    },
  };
}

export default defineConfig({
  base: "/",
  plugins: [react(), serveFixtures(), recordSourceHash()],
  build: { target: "es2022", outDir: OUT_DIR, emptyOutDir: true, sourcemap: false },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
  },
});
