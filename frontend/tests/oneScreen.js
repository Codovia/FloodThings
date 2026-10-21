// One-screen layout helpers: sections can be tabs and details can be popups (no page scrolling).
export async function openTab(page, name) {
  const tab = page.getByRole('tab', { name, exact: true })
  // Tabs appear once their data has loaded; wait briefly, then skip if this layout has no such tab.
  await tab.first().waitFor({ state: 'visible', timeout: 10000 }).catch(() => {})
  if (await tab.count() && await tab.first().getAttribute('aria-selected') !== 'true') await tab.first().click()
}
// Fails the test if the page or any panel scrolls, or anything sits off screen (maps excluded).
export async function expectOneScreen(page) {
  const report = await page.evaluate(() => {
    const scrolls = [...document.querySelectorAll('main, main *')].filter(e => {
      if (e.closest('.leaflet-container') || e.closest('[hidden]') || e.tagName === 'TEXTAREA') return false
      const s = getComputedStyle(e); if (s.display === 'none') return false
      return /(auto|scroll|hidden)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 3 && e.clientHeight > 30
    }).length
    const outside = [...document.querySelectorAll('main *')].filter(e => {
      if (e.closest('[hidden]') || e.closest('.leaflet-container')) return false
      const s = getComputedStyle(e); if (s.display === 'none') return false
      const r = e.getBoundingClientRect(); return r.height > 0 && (r.bottom > innerHeight + 1 || r.right > innerWidth + 1)
    }).length
    return { page: document.documentElement.scrollHeight - innerHeight, width: document.documentElement.scrollWidth - innerWidth, scrolls, outside }
  })
  return report
}
// The place search lists four localities per page: page until the named locality is shown.
export async function findLocality(page, name) {
  const list = page.getByRole('list', { name: 'District localities' }), target = list.getByRole('button', { name: new RegExp(`^${name} —`) })
  await list.getByRole('button').first().waitFor({ state: 'visible' })
  const pager = page.getByRole('navigation', { name: 'More localities' })
  while (!await target.count() && await pager.count() && await pager.getByRole('button', { name: 'Next ›' }).isEnabled()) await pager.getByRole('button', { name: 'Next ›' }).click()
  return target
}
