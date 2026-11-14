// Run with: npm test (node's built-in test runner, no dependencies)
import {test} from 'node:test'
import assert from 'node:assert/strict'
import {rangeStart} from './ranges.js'

test('1M on the 31st clamps to the end of the shorter month (#57)', () => {
  assert.equal(rangeStart('1M', '2026-03-31'), '2026-02-28')
})

test('6M on the 31st clamps to the end of the shorter month (#57)', () => {
  assert.equal(rangeStart('6M', '2026-08-31'), '2026-02-28')
})

test('1M in a leap year clamps to 29 February', () => {
  assert.equal(rangeStart('1M', '2028-03-30'), '2028-02-29')
})

test('1M across the new year', () => {
  assert.equal(rangeStart('1M', '2026-01-15'), '2025-12-15')
})

test('1Y on 29 February clamps to 28 February', () => {
  assert.equal(rangeStart('1Y', '2028-02-29'), '2027-02-28')
})

test('YTD starts on 1 January', () => {
  assert.equal(rangeStart('YTD', '2026-11-14'), '2026-01-01')
})

test('All has no start', () => {
  assert.equal(rangeStart('All', '2026-11-14'), '')
})
