import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"
import { spawnAmbientStars } from "../web/js/ambient-stars.js"

test("ambient stars populate one lightweight texture per star", () => {
  const children = []
  const background = {
    ownerDocument: { createElement: (tag) => {
      const style = {}
      Object.defineProperty(style, "setProperty", { value: (name, value) => { style[name] = value } })
      return { tag, style }
    } },
    querySelector: () => children.find((child) => child.className === "galaxy-hero") || null,
    appendChild: (child) => children.push(child),
  }
  assert.equal(spawnAmbientStars(background, () => 0.5), 14)
  assert.equal(children.length, 14)
  assert.deepEqual(children[0], { tag: "i", className: "galaxy-hero",
    style: { left: "50.00%", top: "50.00%", animationDelay: "2.00s", "--galaxy-star-core": "2px" } })
  assert.equal(spawnAmbientStars(background, () => 0), 0)
  assert.equal(children.length, 14)
  assert.equal(spawnAmbientStars(null), 0)
})
test("ambient stars use a stable texture without promoting the static backdrop", async () => {
  const css = await readFile(new URL("../web/css/galaxy.css", import.meta.url), "utf8")
  const backdrop = css.slice(css.indexOf("#galaxy-bg {"), css.indexOf("#galaxy-bg::before"))
  const starField = css.slice(css.indexOf("#galaxy-bg::before"), css.indexOf("#galaxy-bg .galaxy-hero"))
  const star = css.slice(css.indexOf("#galaxy-bg .galaxy-hero {"), css.indexOf("@keyframes galaxy-twinkle"))

  assert.doesNotMatch(backdrop, /will-change|translateZ/)
  assert.match(starField, /inset: 0/)
  assert.doesNotMatch(starField, /height:\s*200%/)
  assert.match(star, /radial-gradient/)
  assert.doesNotMatch(star, /box-shadow/)
  assert.match(css, /rotateZ\(0\.05deg\) scale\(0\.9\)/)
  assert.match(css, /rotateZ\(0\.05deg\) scale\(1\.2\)/)
  assert.match(css, /body:has\([^)]*\.gx-route-workspace[^)]*\) #galaxy-bg \.galaxy-hero\s*{\s*display: none;/)
  assert.doesNotMatch(css, /animation-play-state/)
})
