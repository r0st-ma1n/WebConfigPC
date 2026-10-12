import test from 'node:test'
import assert from 'node:assert/strict'
import { EXAMPLES, selectExample, updateRecommendParams } from '../src/recommendation-form.js'
const defaultParams = { budget: 100000, scenario: 'gaming', resolution: '1440p', platform: null, cpu_id: null, gpu_id: null }

test('form updates controlled recommendation parameters without losing other fields', () => {
  assert.deepEqual(updateRecommendParams(defaultParams, { budget: 150000 }), { ...defaultParams, budget: 150000 })
  assert.deepEqual(updateRecommendParams(defaultParams, { scenario: 'office' }), { ...defaultParams, scenario: 'office' })
})

test('quick prompt selection returns the selected prompt for controlled text state', () => {
  assert.ok(EXAMPLES.length >= 3)
  assert.equal(selectExample(EXAMPLES[1]), EXAMPLES[1])
})
