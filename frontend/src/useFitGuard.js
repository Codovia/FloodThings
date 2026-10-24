import { useEffect } from 'react'

// One-screen safety net. Pages are designed to fit without scrolling; if content would still be
// cut off (very short window, browser zoom, enlarged text or unusually long data), the page falls
// back to normal scrolling instead of hiding information. Re-checked on resize, page change and content change.
function clipped() {
  const main = document.querySelector('main')
  if (!main) return false
  if (main.scrollHeight > main.clientHeight + 2) return true
  for (const e of main.querySelectorAll('*')) {
    if (e.clientHeight <= 30 || e.tagName === 'TEXTAREA' || e.closest('.leaflet-container')) continue
    if (e.scrollHeight <= e.clientHeight + 3) continue
    const s = getComputedStyle(e)
    if (/(auto|scroll|hidden)/.test(s.overflowY) && !e.closest('[hidden]')) return true
  }
  return false
}

export default function useFitGuard(path) {
  useEffect(() => {
    const root = document.documentElement
    let frame = 0, timer = 0
    // Measure the one-screen layout from scratch, so a moment of clipping while data loads does not
    // leave the page scrolling. Layout is measured synchronously, so nothing flickers; the scroll
    // position is kept when the page still needs to scroll.
    const check = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => {
      const y = window.scrollY
      delete root.dataset.fit
      if (clipped()) { root.dataset.fit = 'scroll'; if (y) window.scrollTo(0, y) }
    }) }
    const throttled = () => { if (!timer) timer = setTimeout(() => { timer = 0; check() }, 400) }
    check()
    const main = document.querySelector('main')
    const mutations = main && typeof MutationObserver !== 'undefined' ? new MutationObserver(throttled) : null
    mutations?.observe(main, { childList: true, subtree: true, characterData: true })
    window.addEventListener('resize', check)
    const late = setTimeout(check, 1500)  // after data and maps settle
    return () => { cancelAnimationFrame(frame); clearTimeout(timer); clearTimeout(late); mutations?.disconnect(); window.removeEventListener('resize', check) }
  }, [path])
}
