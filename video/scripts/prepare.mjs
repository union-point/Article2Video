import { readFileSync, writeFileSync } from "node:fs";
import { storyboardSchema } from "../src/schema.mjs";
// Explicit staging, no hidden linkage to a different article's outputs.
const manifest = JSON.parse(
  readFileSync(process.argv[2] ?? "../output/storyboard.json", "utf8"),
);
storyboardSchema.parse(manifest);
writeFileSync(
  "public/storyboard.json",
  JSON.stringify(manifest, null, 2) + "\n",
);
console.log(
  "Prepared cited storyboard for Studio; narration/export belong to Stage 8.",
);
