import test from "node:test";
import assert from "node:assert/strict";
import { explicitProportion } from "../src/proportion.mjs";
test("explicit approved part/whole wording preserves approximation", () =>
  assert.deepEqual(
    explicitProportion("about nine of every ten sources AI cites"),
    { numerator: 9, denominator: 10, approximate: true },
  ));
test("does not turn unrelated values into a ratio", () =>
  assert.equal(explicitProportion("nine companies and ten websites"), null));
test("rejects invalid or oversized graphic counts", () => {
  assert.equal(explicitProportion("20 out of 10"), null);
  assert.equal(explicitProportion("90 out of 100"), null);
});
