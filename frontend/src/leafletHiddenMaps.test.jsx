import {expect,it} from 'vitest'
import L from 'leaflet'
import './leafletHiddenMaps.js'

const size=(element,width,height)=>{Object.defineProperty(element,'clientWidth',{configurable:true,value:width});Object.defineProperty(element,'clientHeight',{configurable:true,value:height})}

it('defers fitting a map hidden in an inactive tab and applies the latest view once it is shown',()=>{
 const element=document.createElement('div');document.body.appendChild(element);size(element,0,0)
 const map=L.map(element).setView([15.1,76.1],6)
 // Without the guard Leaflet throws "Invalid LatLng object: (NaN, NaN)" here and the page goes blank.
 expect(()=>map.fitBounds([[12,74],[13,75]],{padding:[20,20]})).not.toThrow()
 expect(()=>map.fitBounds([[16,76],[17,77]],{padding:[20,20]})).not.toThrow()
 expect(map.getCenter().lat).toBeCloseTo(15.1)
 size(element,600,400);map.invalidateSize({pan:false})
 expect(map.getCenter().lat).toBeGreaterThan(16);expect(map.getCenter().lat).toBeLessThan(17)
 expect(Number.isFinite(map.getZoom())).toBe(true)
 map.remove();element.remove()
})

it('fits a visible map immediately and lets a hidden new map start from the requested area',()=>{
 const shown=document.createElement('div');document.body.appendChild(shown);size(shown,600,400)
 const visible=L.map(shown).setView([15.1,76.1],6);visible.fitBounds([[12,74],[13,75]])
 expect(visible.getCenter().lat).toBeCloseTo(12.5,0)
 const hiddenBox=document.createElement('div');document.body.appendChild(hiddenBox);size(hiddenBox,0,0)
 const fresh=L.map(hiddenBox);expect(()=>fresh.fitBounds([[12,74],[13,75]],{padding:[8,8]})).not.toThrow()
 expect(fresh.getCenter().lat).toBeCloseTo(12.5,0)
 visible.remove();fresh.remove();shown.remove();hiddenBox.remove()
})
