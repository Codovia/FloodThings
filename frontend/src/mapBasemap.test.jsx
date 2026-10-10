import {expect,it,vi} from 'vitest'
import {addBasemap,OSM_URL,OSM_ATTRIBUTION} from './mapBasemap.js'
it('uses real origin only, visible attribution and ordinary cached viewport tiles',()=>{
 const tile={addTo:vi.fn().mockReturnThis(),on:vi.fn()},L={tileLayer:vi.fn(()=>tile)},map={removeLayer:vi.fn()}
 addBasemap(L,map,vi.fn(),'osm')
 expect(L.tileLayer).toHaveBeenCalledWith(OSM_URL,{maxZoom:19,attribution:OSM_ATTRIBUTION,referrerPolicy:'origin',updateWhenIdle:true,keepBuffer:1})
 expect(tile.addTo).toHaveBeenCalledWith(map)
})
it('one tile failure removes only the background and never retries or changes providers',()=>{
 let fail;const tile={addTo:vi.fn().mockReturnThis(),on:vi.fn((event,fn)=>fail=fn)},L={tileLayer:vi.fn(()=>tile)},map={removeLayer:vi.fn()},notice=vi.fn()
 addBasemap(L,map,notice,'osm');fail();fail()
 expect(map.removeLayer).toHaveBeenCalledExactlyOnceWith(tile);expect(notice).toHaveBeenCalledTimes(1);expect(L.tileLayer).toHaveBeenCalledTimes(1)
})
it.each(['none','unreviewed-provider'])('disabled or unknown configuration requests no tiles (%s)',setting=>{
 const L={tileLayer:vi.fn()},notice=vi.fn();expect(addBasemap(L,{},notice,setting)).toBeNull();expect(L.tileLayer).not.toHaveBeenCalled();expect(notice).toHaveBeenCalledTimes(1)
})
