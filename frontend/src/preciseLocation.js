// Browsers answer a location request with a fast, coarse fix first (Wi-Fi, mobile network or IP)
// and refine it with satellites over the next seconds. Watch for a short time and keep the most
// accurate fix, stopping early once it is good enough. Coordinates stay in memory only.
export const GOOD_ACCURACY_M = 20
// Home and the location picker stop refining here: ±50 m is precise for weather, risk and naming, and a
// phone that stays at ±30–50 m indoors would otherwise make people wait the whole window. Directions use 20.
export const QUICK_ACCURACY_M = 50
export const LOCATE_WAIT_MS = 20000
// The improvement window starts only when the first fix arrives; before that the browser may still be showing
// its permission prompt, which people can take a while to answer.
export const FIRST_FIX_WAIT_MS = 60000

// How to present a fix. Phones can share only an approximate area on purpose: Chrome for Android's prompt
// offers "Approximate (Neighborhood)" (May 2026), and iPhones without "Precise Location" for Safari Websites
// report areas of a few kilometres. Fixes that coarse get the settings advice; the threshold is a heuristic.
export const PRECISE_M = 100
export const APPROXIMATE_SETTING_M = 1000
export const PRECISE_LOCATION_HELP = 'Your phone may be sharing only an approximate location. Android (Chrome): tap the icon left of the address → Permissions → Location → Precise. iPhone: Settings → Privacy & Security → Location Services → Safari Websites → turn on Precise Location. Then tap "Use my location" again.'
export function locationQuality(accuracy) {
  if (!Number.isFinite(accuracy) || accuracy < 0) return null
  const shown = accuracy < 1000 ? `±${Math.round(accuracy)} m` : `±${(accuracy / 1000).toFixed(1)} km`
  if (accuracy <= PRECISE_M) return { level: 'precise', label: 'Precise', shown }
  if (accuracy <= APPROXIMATE_SETTING_M) return { level: 'rough', label: 'Rough', shown, advice: 'Move outdoors or near a window, then tap "Use my location" again.' }
  return { level: 'approximate', label: 'Approximate', shown, advice: PRECISE_LOCATION_HELP }
}

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
