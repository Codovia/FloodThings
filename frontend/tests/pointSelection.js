// Controlled GPS replaces retired public coordinate-form steps. No provider call.
export async function selectPoint(page,latitude,longitude) {
 await page.context().grantPermissions(['geolocation'])
 await page.context().setGeolocation({latitude,longitude,accuracy:40})
 // "Change location" is a popup; it closes by itself once GPS sets the point.
 const change=page.getByRole('button',{name:'Change location'})
 if(await change.count() && !await page.getByRole('button',{name:'Use my GPS location'}).isVisible())await change.click()
 await page.getByRole('button',{name:'Use my GPS location'}).click()
}

// Home shows the weather of the chosen place (the Weather page was merged into it). Choose the place with the
// location control on Shelters, then return to Home — in-app navigation, so state and the page clock are kept.
export async function goInApp(page, path) {
 await page.evaluate(next => { window.history.pushState(null, '', next); window.dispatchEvent(new PopStateEvent('popstate')) }, path)
}
export async function choosePlaceForHome(page, latitude, longitude) {
 await goInApp(page, '/shelters'); await selectPoint(page, latitude, longitude)
 await page.locator('.selected-point-name').filter({ hasText: `${Number(latitude.toFixed(4))}°` }).first().waitFor()   // the place is set before Home opens (the bar rounds to 4 decimals)
 await goInApp(page, '/')
}
// Shelters may also locate on its own once permission is granted, naming the same GPS point "Your GPS location".
export const GPS_POINT_NAME = /^(GPS-selected point|Your GPS location)$/
