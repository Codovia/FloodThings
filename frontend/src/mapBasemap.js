// Only ordinary viewport tiles: no proxy, identity spoofing, prefetch or retries.
export const OSM_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
export const OSM_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
export const BASEMAP_NOTICE = 'Background tiles are unavailable. Geographic overlays and coordinate selection remain usable; a missing background does not establish flood absence.'

export function addBasemap(leaflet, map, onUnavailable, setting = import.meta.env.VITE_MAP_BASEMAP || 'osm') {
  if (setting !== 'osm') {
    onUnavailable()
    return null
  }
  const tiles = leaflet.tileLayer(OSM_URL, {
    maxZoom: 19, attribution: OSM_ATTRIBUTION,
    // The app's same-origin header remains intact. Send only its real origin
    // for these public images, never the admin path, query or credentials.
    referrerPolicy: 'origin', updateWhenIdle: true, keepBuffer: 1,
  }).addTo(map)
  let stopped = false
  tiles.on('tileerror', () => {
    if (stopped) return
    stopped = true
    map.removeLayer(tiles)
    onUnavailable()
  })
  return tiles
}
