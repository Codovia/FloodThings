import { useLayoutEffect, useRef, useState } from 'react'

// Fit only when the essential rows leave enough space for a readable workspace.
// Large text, zoomed/narrow browsers and short screens keep natural page scrolling.
export default function useHomeViewport() {
  const dashboard = useRef(null)
  const [fits, setFits] = useState(false)
  useLayoutEffect(() => {
    const element = dashboard.current
    if (!element) return
    const main = element.closest('main')
    if (!main) return
    const nodes = [document.querySelector('.app-header'), document.querySelector('.app-footer'), main.querySelector('.page-intro'), element.querySelector('.home-location-bar'), element.querySelector('.home-summary-cards'), element.querySelector('.home-essential-status')]
    let frame
    function measure() {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (innerWidth < 1100 || innerHeight < 740 || nodes.some(n => !n)) { setFits(false); return }
        const [header, footer, intro, location, cards, essential] = nodes
        const mainStyle = getComputedStyle(main), introStyle = getComputedStyle(intro), layoutStyle = getComputedStyle(element)
        const reserved = [header, footer, intro, location, cards].reduce((total, n) => total + n.getBoundingClientRect().height, 0)
          + parseFloat(mainStyle.paddingTop) + parseFloat(mainStyle.paddingBottom)
          + parseFloat(introStyle.marginTop) + parseFloat(introStyle.marginBottom) + 2 * parseFloat(layoutStyle.rowGap)
        const available = innerHeight - reserved
        setFits(available >= Math.max(320, essential.scrollHeight + 110))
      })
    }
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    for (const n of [...nodes, main]) if (n) observer?.observe(n)
    window.addEventListener('resize', measure)
    document.fonts?.addEventListener?.('loadingdone', measure)
    measure()
    return () => { cancelAnimationFrame(frame); observer?.disconnect(); window.removeEventListener('resize', measure); document.fonts?.removeEventListener?.('loadingdone', measure) }
  }, [])
  return { dashboard, fits }
}
