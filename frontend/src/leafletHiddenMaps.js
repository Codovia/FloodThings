import L from 'leaflet'

// One-screen layouts keep maps mounted in inactive tabs, where the container is 0×0 px. Leaflet
// cannot fit or centre such a map: it computes NaN coordinates and throws, which blanks the page.
// While a map is hidden, keep only its latest view request and apply it once the map is shown
// (useMapResize calls invalidateSize, which fires 'resize').
const VIEW_METHODS = ['fitBounds', 'setView', 'flyTo', 'flyToBounds', 'panTo']
const hidden = map => { const box = map.getContainer?.(); return !box || !box.clientWidth || !box.clientHeight }

export function guardHiddenMaps(leaflet = L) {
  const proto = leaflet?.Map?.prototype
  if (!proto || proto.__hiddenMapGuard) return
  proto.__hiddenMapGuard = true
  const original = Object.fromEntries(VIEW_METHODS.filter(name => proto[name]).map(name => [name, proto[name]]))
  function applyPending() {
    const pending = this._pendingView
    if (!pending || hidden(this)) return
    this._pendingView = null
    original[pending.name].apply(this, pending.args)
  }
  for (const [name, method] of Object.entries(original)) {
    proto[name] = function (...args) {
      if (!hidden(this)) { this._pendingView = null; return method.apply(this, args) }
      // A hidden map still needs a first centre so layers can be added; a fixed zoom is safe at 0×0.
      if (!this._loaded) {
        const center = name === 'setView' || name === 'flyTo' || name === 'panTo' ? args[0] : leaflet.latLngBounds(args[0]).getCenter()
        original.setView.call(this, center, name === 'setView' || name === 'flyTo' ? args[1] ?? 6 : 6, { animate: false })
        if (name === 'setView') return this
      }
      this._pendingView = { name, args }
      if (!this._pendingListener) { this._pendingListener = true; this.on('resize', applyPending, this) }
      return this
    }
  }
}

guardHiddenMaps()
