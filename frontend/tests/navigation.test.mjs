import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

test('navigation exposes the requested pages and uses history-based links', async () => {
  const [router, app] = await Promise.all([
    readFile(new URL('../src/router.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/App.tsx', import.meta.url), 'utf8'),
  ])
  for (const route of ['/', '/recommend', '/manual', '/info']) assert.ok(app.includes(`'${route}'`))
  assert.match(router, /history\.pushState/)
  assert.match(router, /popstate/)
  assert.match(app, /aria-label="Главная навигация"/)
})
