import test from "node:test";
import assert from "node:assert/strict";
import { assetsInScope } from "../src/lib/workspace.ts";

const assets = [
  { id: "a", project_name: "Album/Song A" },
  { id: "b", project_name: "Album/Song B" },
  { id: "c", project_name: "Other" },
];

test("a smart collection returns only its matching files", () => {
  assert.deepEqual(assetsInScope(assets, "All Projects", ["b"]), [assets[1]]);
});
test("an empty collection stays empty rather than showing the entire library", () => {
  assert.deepEqual(assetsInScope(assets, "All Projects", []), []);
});
test("album scope includes descendants but excludes unrelated projects", () => {
  assert.deepEqual(assetsInScope(assets, "Album"), assets.slice(0, 2));
  assert.deepEqual(assetsInScope(assets, "Album/Song A"), [assets[0]]);
});
test("clearing collection scope restores all files", () => {
  assert.deepEqual(assetsInScope(assets, "All Projects"), assets);
});
