// Internal worker: the Python command supplies provenance-checked, frozen assets.
import { readFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { storyboardSchema } from "../src/schema.mjs";

const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const manifest = storyboardSchema.parse(job.manifest);
const inputProps = {
  manifest,
  captions: job.timings.scenes.flatMap((scene) =>
    scene.sentences.map(({ text, start, end }) => ({ text, start, end })),
  ),
  narration: "narration.wav",
  narrationVolume: job.narration_volume,
};
let serveUrl;
try {
  serveUrl = await bundle({
    entryPoint: resolve("src/index.ts"),
    publicDir: job.public_dir,
    rspack: true,
  });
  const composition = await selectComposition({
    serveUrl,
    id: "Storyboard",
    inputProps,
  });
  let last = -1;
  await renderMedia({
    serveUrl,
    composition,
    inputProps,
    outputLocation: job.output,
    codec: "h264",
    audioCodec: "aac",
    audioBitrate: "192k",
    pixelFormat: "yuv420p",
    crf: 18,
    scale: job.scale,
    concurrency: job.concurrency,
    overwrite: false,
    onProgress: ({ progress }) => {
      const percent = Math.floor(progress * 20) * 5;
      if (percent > last) {
        console.log(`Rendering ${percent}%`);
        last = percent;
      }
    },
  });
} finally {
  if (serveUrl) rmSync(serveUrl, { recursive: true, force: true });
}
