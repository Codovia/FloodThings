// Browsers answer a location request with a fast, coarse fix first (Wi-Fi, mobile network or IP)
// and refine it with satellites over the next seconds. Watch for a short time and keep the most
// accurate fix, stopping early once it is good enough. Coordinates stay in memory only.
export const GOOD_ACCURACY_M = 20
export const LOCATE_WAIT_MS = 20000
// The improvement window starts only when the first fix arrives; before that the browser may still be showing
// its permission prompt, which people can take a while to answer.
export const FIRST_FIX_WAIT_MS = 60000

const valid = p => Number.isFinite(p?.coords?.latitude) && Math.abs(p.coords.latitude) <= 90 && Number.isFinite(p.coords.longitude) &&
  Math.abs(p.coords.longitude) <= 180 && Number.isFinite(p.coords.accuracy) && p.coords.accuracy >= 0 && Number.isFinite(p.timestamp)

export function preciseLocation({ wait = LOCATE_WAIT_MS, good = GOOD_ACCURACY_M, onProgress = null, signal = null, firstFixWait = FIRST_FIX_WAIT_MS } = {}) {
  return new Promise((resolve, reject) => {
    const geo = navigator.geolocation
    let best = null, done = false, watch = null
    const finish = error => {
      if (done) return
      done = true; clearTimeout(timer); signal?.removeEventListener?.('abort', abort)
      if (watch !== null) geo.clearWatch?.(watch)
      if (signal?.aborted) reject(Object.assign(new Error('Location request cancelled'), { name: 'AbortError' }))
      else if (best) resolve(best)
      else reject(error || Object.assign(new Error('Location request timed out'), { code: 3 }))
    }
    const abort = () => finish()
    let timer = setTimeout(() => finish(), firstFixWait)
    signal?.addEventListener?.('abort', abort)
    const seen = p => {
      if (done || !valid(p)) return
      if (!best) { clearTimeout(timer); timer = setTimeout(() => finish(), wait) }  // improvement window starts now
      if (!best || p.coords.accuracy < best.coords.accuracy) { best = p; onProgress?.(p) }
      if (p.coords.accuracy <= good) finish()
    }
    // A refusal ends the attempt; other errors keep the best fix so far, if any.
    const failed = error => finish(error)
    const options = { enableHighAccuracy: true, maximumAge: 0, timeout: firstFixWait }
    try {
      if (geo.watchPosition) watch = geo.watchPosition(seen, failed, options)
      else geo.getCurrentPosition(p => { seen(p); finish() }, failed, options)
    } catch (error) { finish(error) }
  })
}
