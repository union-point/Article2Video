import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { storyboardSchema } from "../src/schema.mjs";
const fixture = () =>
  JSON.parse(
    readFileSync(
      new URL("./fixtures/storyboard.json", import.meta.url),
      "utf8",
    ),
  );
test("accepts complete fixture", () =>
  assert.equal(storyboardSchema.safeParse(fixture()).success, true));
for (const [name, mutate] of Object.entries({
  "unknown color": (m) => {
    m.scenes[0].color = "red";
  },
  "invented chart": (m) => {
    m.scenes[1].component = "bar_chart";
  },
  "missing citations": (m) => {
    m.scenes[0].elements[0].source_ids = [];
  },
  "duplicate scene": (m) => {
    m.scenes[1].scene_id = m.scenes[0].scene_id;
  },
  "timeline gap": (m) => {
    m.scenes[1].start_frame++;
  },
  "adjacent repetition": (m) => {
    m.scenes[2].component = m.scenes[1].component;
  },
  "long title": (m) => {
    m.scenes[0].elements[0].text = "X".repeat(81);
  },
  "element overflow": (m) => {
    m.scenes[0].elements[0].end_frame = m.duration_frames + 1;
  },
  "missing conclusion": (m) => {
    m.scenes.at(-1).component = "ranking";
  },
}))
  test(`rejects ${name}`, () => {
    const m = fixture();
    mutate(m);
    assert.equal(storyboardSchema.safeParse(m).success, false);
  });
