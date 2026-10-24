// The isolated test backend has no shelter database. Layout tests that only need the
// genuine empty state use this labelled fixture: an available live directory with zero shelters.
export async function emptyShelterDirectory(page){
 await page.route('**/api/shelters*',async route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'available',mode:'live',shelters:[],total:0,limit:100,offset:0,retrieved_at:await page.evaluate(()=>new Date().toISOString()),verification_valid_hours:24})}))
}
