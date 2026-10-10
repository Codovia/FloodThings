// Browser-restricted PUBLIC MapTiler key only; never a service token.
export function adminMapSettings(env=import.meta.env) {
  const enabled=env.VITE_ADMIN_MAP_PROVIDER==='maptiler' && env.VITE_ADMIN_MAP_TERMS_ACCEPTED==='true' && !!env.VITE_MAPTILER_PUBLIC_KEY
  return {enabled,publicKey:enabled?env.VITE_MAPTILER_PUBLIC_KEY:null}
}
export function tileMetadataURL(mode,settings) {
  if(!settings.enabled || !['satellite','hybrid'].includes(mode)) throw Error('Authorized imagery is not configured')
  return `https://api.maptiler.com/maps/${mode}/256/tiles.json?key=${encodeURIComponent(settings.publicKey)}`
}
export function validatedTileMetadata(data) {
  if(!Array.isArray(data?.tiles)||!data.tiles.length||!Number.isInteger(data.maxzoom)||data.maxzoom<0||data.maxzoom>22)throw Error('Invalid imagery metadata')
  const template=data.tiles[0],url=new URL(template)
  if(url.protocol!=='https:'||url.hostname!=='api.maptiler.com'||url.username||url.password||!['{z}','{x}','{y}'].every(t=>template.includes(t)))throw Error('Invalid imagery metadata')
  const doc=new DOMParser().parseFromString(data.attribution||'', 'text/html')
  const credit=(doc.body.textContent||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
  return {url:template,maxZoom:data.maxzoom,attribution:`<a href="https://www.maptiler.com/copyright/">© MapTiler</a> · <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a>${credit?' · '+credit:''}`}
}
export function validatedSearchResults(data) {
  if(data?.type!=='FeatureCollection'||!Array.isArray(data.features)||data.features.length>5)throw Error('Invalid search response')
  return data.features.map(f=>{
    const c=f.geometry?.coordinates,name=f.place_name||f.text
    if(f.geometry?.type!=='Point'||!Array.isArray(c)||c.length<2||!c.every(Number.isFinite)||c[0]<74||c[0]>78.6||c[1]<11.5||c[1]>18.6||typeof name!=='string'||!name.trim())throw Error('Invalid search response')
    return {id:String(f.id||name),name,latitude:c[1],longitude:c[0]}
  })
}
export function buildingSearchURL(query,settings) {
  if(!settings.enabled||query.trim().length<3||query.trim().length>120)throw Error('Invalid building search')
  return `https://api.maptiler.com/geocoding/${encodeURIComponent(query.trim())}.json?${new URLSearchParams({key:settings.publicKey,limit:'5',country:'in',bbox:'74,11.5,78.6,18.6'})}`
}
