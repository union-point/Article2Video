import { readFileSync } from "node:fs";
import { storyboardSchema } from "../src/schema.mjs";
try {
  storyboardSchema.parse(
    JSON.parse(readFileSync(process.argv[2] ?? 0, "utf8")),
  );
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
