// Language rules (ENGINEERING.md 24.7), with the review's MF-10 fix: whole words and phrases,
// not substrings, so "threshold", "Holdings" and "uncertainty" do not trip the test, while
// "buy", "hold" or "target price" anywhere in the UI source fails the build.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { COPY } from "./copy";

const BANNED = [
  /\bbuy(s|ing)?\b/i,
  /\bsell(s|ing)?\b/i,
  /\bhold\b/i,
  /\btarget price\b/i,
  /\bsignals?\b/i,
  /\brecommend(ation|ations|ed|s)?\b/i,
  /\bguarantee(d|s)?\b/i,
  /\bwill reach\b/i,
  /\bcertain(ly)?\b/i,
];

function offences(text: string): string[] {
  return BANNED.filter((pattern) => pattern.test(text)).map((pattern) => pattern.source);
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "types" ? [] : sourceFiles(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

// String literals and JSX text: what a user can read. Comments are not visible, so they go first.
function visibleText(source: string): string[] {
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const strings = [...code.matchAll(/(["'`])((?:\\.|(?!\1).)*)\1/g)].map((m) => m[2] ?? "");
  const jsxText = [...code.matchAll(/>([^<>{}]+)</g)].map((m) => m[1] ?? "");
  return [...strings, ...jsxText];
}

describe("language rules", () => {
  it("flags banned words and phrases", () => {
    expect(offences("Forecast on hold")).not.toEqual([]);
    expect(offences("Our target price is 30")).not.toEqual([]);
    expect(offences("a buy signal")).not.toEqual([]);
  });

  it("does not flag legitimate words that contain banned ones", () => {
    expect(offences("Equity Group Holdings, threshold, uncertainty, shareholders, selling")).toEqual(
      ["\\bsell(s|ing)?\\b"],
    );
    expect(offences("Equity Group Holdings, threshold, uncertainty, shareholders")).toEqual([]);
  });

  it("keeps every UI string inside the rules", () => {
    const problems: string[] = [];
    const copyText = JSON.stringify(COPY, (_key, value: unknown) =>
      typeof value === "function" ? value("2026-10-07", "2026-10-07", "2026-10-07", "2026-10-07") : value,
    );
    if (offences(copyText).length) problems.push(`copy.ts: ${offences(copyText).join(", ")}`);
    for (const file of sourceFiles(join(__dirname, ".."))) {
      for (const text of visibleText(readFileSync(file, "utf8"))) {
        const found = offences(text);
        if (found.length) problems.push(`${file}: "${text.trim()}" (${found.join(", ")})`);
      }
    }
    expect(problems).toEqual([]);
  });
});
