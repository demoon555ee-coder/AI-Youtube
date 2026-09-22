import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const root = process.cwd();
let ts;
try {
  const require = createRequire(import.meta.url);
  ts = require("typescript");
} catch {
  const globalRoot = execFileSync("npm", ["root", "-g"], { encoding: "utf8" }).trim();
  ts = await import(pathToFileURL(path.join(globalRoot, "typescript", "lib", "typescript.js")).href);
  ts = ts.default ?? ts;
}

const files = [];
function walk(dir) {
  for (const name of fs.readdirSync(dir)) {
    if (["node_modules", "playwright-report", "test-results"].includes(name)) continue;
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) walk(full);
    else if (/\.(ts|tsx)$/.test(name)) files.push(full);
  }
}
walk(root);

const errors = [];
for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  const kind = file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  for (const diagnostic of source.parseDiagnostics ?? []) {
    errors.push({ file: path.relative(root, file), message: ts.flattenDiagnosticMessageText(diagnostic.messageText, " ") });
  }
}

console.log(JSON.stringify({ files: files.length, errors }, null, 2));
process.exitCode = errors.length ? 1 : 0;
