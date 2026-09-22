import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const ROOT = path.resolve(new URL('..', import.meta.url).pathname);
const require = createRequire(import.meta.url);
let ts;
try {
  ts = require('typescript');
} catch {
  console.error('typescript dependency is unavailable; run npm install in frontend or provide NODE_PATH');
  process.exit(2);
}

let files = 0;
const errors = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (['node_modules', '.next'].includes(entry.name)) continue;
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (/\.(ts|tsx)$/.test(entry.name)) {
      files += 1;
      const kind = entry.name.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
      const source = fs.readFileSync(file, 'utf8');
      const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, kind);
      for (const diagnostic of sf.parseDiagnostics ?? []) {
        errors.push({ file, message: ts.flattenDiagnosticMessageText(diagnostic.messageText, ' ') });
      }
    }
  }
}
walk(path.join(ROOT, 'frontend'));
console.log(JSON.stringify({ files, errors }, null, 2));
process.exit(errors.length ? 1 : 0);
