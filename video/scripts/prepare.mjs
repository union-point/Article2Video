import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { storyboardSchema } from "../src/schema.mjs";
// Explicit staging, no hidden linkage to a different article's outputs.
const manifestPath = process.argv[2] ?? "../output/storyboard.json";
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const timings = JSON.parse(
  readFileSync(join(dirname(manifestPath), "timings.json"), "utf8"),
);
if (
  timings.duration_frames !== manifest.duration_frames ||
  timings.fps !== manifest.fps ||
  timings.scenes.length !== manifest.scenes.length ||
  timings.scenes.some(
    (scene, index) =>
      scene.scene_id !== manifest.scenes[index].scene_id ||
      scene.start_frame !== manifest.scenes[index].start_frame ||
      scene.duration_frames !== manifest.scenes[index].duration_frames,
  )
) {
  throw new Error("Timings do not match storyboard duration and frame rate");
}
storyboardSchema.parse(manifest);
writeFileSync(
  "public/storyboard.json",
  JSON.stringify(manifest, null, 2) + "\n",
);
writeFileSync(
  "public/captions.json",
  JSON.stringify(
    timings.scenes.flatMap((scene) =>
      scene.sentences.map(({ text, start, end }) => ({ text, start, end })),
    ),
    null,
    2,
  ) + "\n",
);
console.log(
  "Prepared cited storyboard for Studio; narration/export belong to Stage 8.",
);
