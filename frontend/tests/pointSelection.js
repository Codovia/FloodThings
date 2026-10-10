// Controlled GPS replaces retired public coordinate-form steps. No provider call.
export async function selectPoint(page,latitude,longitude) {
 await page.context().grantPermissions(['geolocation'])
 await page.context().setGeolocation({latitude,longitude,accuracy:40})
 const disclosure=page.getByText('Change location',{exact:true})
 if(await disclosure.count() && !await page.getByRole('button',{name:'Use my GPS location'}).isVisible())await disclosure.click()
 await page.getByRole('button',{name:'Use my GPS location'}).click()
}
