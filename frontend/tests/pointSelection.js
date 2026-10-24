// Controlled GPS replaces retired public coordinate-form steps. No provider call.
export async function selectPoint(page,latitude,longitude) {
 await page.context().grantPermissions(['geolocation'])
 await page.context().setGeolocation({latitude,longitude,accuracy:40})
 // "Change location" is a popup; it closes by itself once GPS sets the point.
 const change=page.getByRole('button',{name:'Change location'})
 if(await change.count() && !await page.getByRole('button',{name:'Use my GPS location'}).isVisible())await change.click()
 await page.getByRole('button',{name:'Use my GPS location'}).click()
}
