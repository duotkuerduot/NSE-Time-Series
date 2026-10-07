import { readFile, stat } from "node:fs/promises";
import { resolve, sep } from "node:path";
import react from "@vitejs/plugin-react";
import type { Connect, Plugin } from "vite";
import { defineConfig } from "vitest/config";

const FIXTURES = resolve(import.meta.dirname, "../contracts/api/v1/fixtures");

// Serves the contract fixtures at /api/v1 so every page renders without a pipeline
// (Phase 0 acceptance: "the frontend can render every page from fixtures").
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

export default defineConfig({
  plugins: [react(), serveFixtures()],
  build: { target: "es2022", sourcemap: true },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
  },
});
