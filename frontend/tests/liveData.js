// Home asks the server for live risk (Open-Meteo rain, GloFAS river flow, elevation) for every chosen place. Tests that
// are not about risk answer those requests in the browser, so a test run does not spend this network's free Open-Meteo
// allowance (5,000 calls an hour). risk-features.spec.js remains the deliberate live check.
const LIVE_RISK = new Set(['/api/risk', '/api/risk/area', '/api/risk/grid', '/api/river-forecast'])
export async function withoutLiveRisk(page) {
  await page.route(url => LIVE_RISK.has(url.pathname) || url.pathname.startsWith('/api/ai/'), route => route.fulfill({
    status: 503, contentType: 'application/json',
    body: JSON.stringify({ status: 'unavailable', message: 'TEST: live risk is not requested in this test.' }) }))
}
