// Unit tests run at laptop width by default: below 1100 px the one-screen layout turns sections into tabs.
// A test can still stub window.matchMedia itself to check the phone layout.
if (!window.matchMedia) {
  window.matchMedia = query => ({ matches: /min-width:\s*1100px/.test(query), media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent() { return false } })
}
