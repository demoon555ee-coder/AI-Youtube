import {bundle} from "@remotion/bundler";
import {getCompositions, renderMedia} from "@remotion/renderer";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const args = process.argv.slice(2);

const readArg = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};

const inputPath = readArg("--input");
if (!inputPath) {
  throw new Error("Missing --input manifest path");
}

const absoluteInput = path.resolve(inputPath);
const manifest = JSON.parse(await fs.readFile(absoluteInput, "utf8"));
const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), ".");
const publicDir = manifest.publicDir ?? path.join(projectRoot, "public");

await fs.mkdir(path.dirname(manifest.outputPath), {recursive: true});

const serveUrl = await bundle({
  entryPoint: path.join(projectRoot, "src/index.ts"),
  publicDir,
  webpackOverride: (config) => config,
});

const compositions = await getCompositions(serveUrl, {
  inputProps: manifest,
  logLevel: "error",
});

const composition = compositions.find((item) => item.id === manifest.compositionId);
if (!composition) {
  throw new Error(`Composition not found: ${manifest.compositionId}`);
}

await renderMedia({
  composition,
  serveUrl,
  codec: "h264",
  outputLocation: manifest.outputPath,
  inputProps: manifest,
  crf: 20,
  concurrency: manifest.concurrency ?? 2,
});

console.log(JSON.stringify({
  status: "completed",
  outputPath: manifest.outputPath,
  durationInFrames: composition.durationInFrames,
  fps: composition.fps,
}));
