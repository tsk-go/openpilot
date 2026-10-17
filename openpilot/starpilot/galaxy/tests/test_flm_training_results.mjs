import assert from "node:assert/strict"
import { compile } from "../web/vendor/vue/vue.esm-browser.js"
import { FLMTrainingResults, validTrainingResults, trainingSummary, detailText } from "../web/js/flm-training-results.js"

const report = () => ({ version: 1, current: { fresh: true, ageSeconds: .1, enabled: true,
  status: "collecting", reason: "independent_evidence", progress: { samples: 140, blocks: 3, requiredBlocks: 16 },
  fit: null, application: { applied: false, reason: "No fit has passed validation" },
  details: { accepted_samples: 140, rejected_reasons: { steering_override: 4 }, coordinates: [0, 0] } }, history: [] })
assert(validTrainingResults(report()))
const counters = report(); counters.current.details.rejected_reasons = Object.fromEntries(Array.from({ length: 24 }, (_, i) => [`reason_${i}`, i]))
assert(validTrainingResults(counters))
assert(validTrainingResults({ version: 1, current: null, history: [] }))
const missing = report(); missing.current.progress.samples = null
assert(validTrainingResults(missing))
assert.equal(detailText(null), "Not reported")
assert.equal(detailText({ steering_override: 4 }), "steering override: 4")
assert.match(trainingSummary({ version: 1, current: null, history: [] }), /No training results/)
const stale = report(); stale.current.fresh = false
assert.match(trainingSummary(stale), /Saved report only/)
assert.match(trainingSummary(report(), "Disconnected"), /out of date/)
for (const mutate of [value => value.current.progress.blocks = -1,
  value => value.current.ageSeconds = Infinity, value => value.current.fit = { status: "rejected", reason: "x" },
  value => value.history = Array.from({ length: 21 }, () => ({ time: "now", status: "collecting", reason: "x", applied: false })),
  value => value.current.details = { invalid: { nested: { deeper: { too_deep: true } } } }]) {
  const value = report(); mutate(value); assert(!validTrainingResults(value))
}
compile(FLMTrainingResults.template, { decodeEntities: value => value.replaceAll("&amp;", "&") })
assert.match(FLMTrainingResults.template, />View FLM training results</)
assert.doesNotMatch(FLMTrainingResults.template, /v-html/)
assert.match(FLMTrainingResults.template, /Last controller report/)
assert.match(FLMTrainingResults.template, /Correction reported applied/)
assert.match(FLMTrainingResults.template, /seconds old when read/)

function instance() {
  const vm = { ...FLMTrainingResults.data(), open: true, activePage: true, mode: "local", unauthorized: () => vm.auth++, auth: 0,
    poller: { stop() {} } }
  for (const [key, method] of Object.entries(FLMTrainingResults.methods)) vm[key] = method.bind(vm)
  for (const [key, computed] of Object.entries(FLMTrainingResults.computed)) Object.defineProperty(vm, key, { get: () => computed.call(vm) })
  return vm
}
const originalFetch = globalThis.fetch
try {
  const calls = []
  globalThis.fetch = async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => report() } }
  const vm = instance()
  await vm.load()
  assert.equal(vm.report.current.progress.blocks, 3)
  assert.equal(calls[0].url, "./api/flm/training-results")
  assert.equal(calls[0].options.method, undefined)
  assert.equal(calls[0].options.cache, "no-store")
  assert.equal(calls[0].options.credentials, "same-origin")
  vm.report.current.application.applied = true
  assert.equal(vm.currentApplied, true)
  globalThis.fetch = async () => { throw new TypeError("offline") }
  await vm.load()
  assert.equal(vm.currentApplied, false)
  assert.match(vm.summary, /out of date/)
  assert.equal(vm.report.current.progress.blocks, 3)
  globalThis.fetch = async () => ({ ok: false, status: 401, json: async () => ({ error: "Sign in" }) })
  await vm.load(); assert.equal(vm.auth, 1)

  let resolve
  globalThis.fetch = () => new Promise(done => { resolve = done })
  const closed = instance()
  const pending = closed.load()
  closed.close()
  resolve({ ok: true, json: async () => report() })
  await pending
  assert.equal(closed.report, null)
  assert.equal(closed.loading, false)
  const count = calls.length
  await closed.load()
  assert.equal(calls.length, count)
} finally { globalThis.fetch = originalFetch }
console.log("FLM results: bounded report, stale/no-data, read-only polling, auth, close cancellation and escaped rendering passed")
