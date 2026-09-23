import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import {fileURLToPath} from "node:url";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(projectRoot, "public");
await fs.mkdir(publicDir, {recursive: true});

const manifestPath = "/tmp/remotion-smoke-manifest.json";
const outputPath = "/tmp/remotion-smoke.mp4";

const manifest = {
  compositionId: "YouTubeAIVideo",
  width: 1920,
  height: 1080,
  fps: 30,
  durationInFrames: 45,
  scenes: [
    {
      scene: 1,
      durationFrames: 45,
      asset: {kind: "color", color: "#111827"},
      onScreenText: "Remotion runtime smoke test",
    },
  ],
  captions: [],
  outputPath,
  publicDir,
  concurrency: 1,
};

await fs.writeFile(manifestPath, JSON.stringify(manifest, null, 2), "utf8");

const child = process.spawn(
  process.execPath,
  ["render.mjs", "--input", manifestPath],
  {
    cwd: projectRoot,
    stdio: "inherit",
  },
);

const exitCode = await new Promise((resolve, reject) => {
  child.once("error", reject);
  child.once("exit", (code) => resolve(code ?? 1));
});

if (exitCode !== 0) {
  throw new Error(`Remotion smoke render failed with exit code ${exitCode}`);
}

const stat = await fs.stat(outputPath);
if (stat.size < 1000) {
  throw new Error(`Remotion smoke output is unexpectedly small: ${stat.size} bytes`);
}

console.log(JSON.stringify({
  status: "passed",
  outputPath,
  bytes: stat.size,
}));
