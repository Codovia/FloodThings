import {expect,it} from 'vitest'
import {adminMapSettings,tileMetadataURL,validatedTileMetadata,buildingSearchURL,validatedSearchResults} from './adminMapProvider.js'
const settings={enabled:true,publicKey:'ISOLATED_PUBLIC_BROWSER_KEY'}
it('requires explicit provider, accepted terms and a public browser key',()=>{
 expect(adminMapSettings({})).toEqual({enabled:false,publicKey:null})
 expect(adminMapSettings({VITE_ADMIN_MAP_PROVIDER:'maptiler',VITE_MAPTILER_PUBLIC_KEY:settings.publicKey})).toEqual({enabled:false,publicKey:null})
 expect(adminMapSettings({VITE_ADMIN_MAP_PROVIDER:'maptiler',VITE_ADMIN_MAP_TERMS_ACCEPTED:'true',VITE_MAPTILER_PUBLIC_KEY:settings.publicKey})).toEqual(settings)
 expect(()=>tileMetadataURL('hybrid',{enabled:false})).toThrow()
})
it('satellite and hybrid are distinct official TileJSON requests',()=>{
 expect(tileMetadataURL('satellite',settings)).toContain('/maps/satellite/256/tiles.json?')
 expect(tileMetadataURL('hybrid',settings)).toContain('/maps/hybrid/256/tiles.json?')
 expect(()=>tileMetadataURL('guessed-provider',settings)).toThrow()
})
it('retains imagery credits and rejects unauthorized tile hosts or invalid metadata',()=>{
 const data={tiles:['https://api.maptiler.com/maps/hybrid/256/{z}/{x}/{y}.jpg'],maxzoom:20,attribution:'© Imagery supplier <img src=x onerror="alert(1)">'}
 const meta=validatedTileMetadata(data);expect(meta.attribution).toContain('Imagery supplier');expect(meta.attribution).toContain('© MapTiler');expect(meta.attribution).not.toContain('<img');expect(meta.maxZoom).toBe(20)
 expect(()=>validatedTileMetadata({...data,tiles:['http://unapproved.example/{z}/{x}/{y}.jpg']})).toThrow()
 expect(()=>validatedTileMetadata({...data,maxzoom:100})).toThrow()
})
it('building searches are explicit, bounded, encoded and India-filtered',()=>{
 const u=new URL(buildingSearchURL('School & Hall',settings));expect(u.pathname).toBe('/geocoding/School%20%26%20Hall.json');expect(u.searchParams.get('limit')).toBe('5');expect(u.searchParams.get('country')).toBe('in');expect(u.searchParams.get('bbox')).toBe('74,11.5,78.6,18.6')
 expect(()=>buildingSearchURL('x',settings)).toThrow()
})
it('reference results preserve longitude/latitude and never certify an entrance',()=>{
 const result=validatedSearchResults({type:'FeatureCollection',features:[{id:'test',place_name:'TEST REFERENCE ONLY',geometry:{type:'Point',coordinates:[74.7,13.5]}}]})
 expect(result).toEqual([{id:'test',name:'TEST REFERENCE ONLY',latitude:13.5,longitude:74.7}]);expect(result[0]).not.toHaveProperty('verified')
 expect(()=>validatedSearchResults({type:'FeatureCollection',features:[{place_name:'Wrong country',geometry:{type:'Point',coordinates:[0,0]}}]})).toThrow()
})
