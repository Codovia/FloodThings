import React,{useEffect,useRef,useState} from 'react'
import L from 'leaflet'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import {tileMetadataURL,validatedTileMetadata} from './adminMapProvider.js'
import useMapResize from './useMapResize.js'
import { boundary } from './homeGeography.js'
import 'leaflet/dist/leaflet.css'

export default function ShelterMap({points=[],route=null,origin=null,onSelect=null,label='Shelter entrance map',mode='street',providerSettings=null,inspection=false,navigationBounds=null,onInspect=null,focus=null}) {
  const container=useRef(null),map=useRef(null),layers=useRef(null),choose=useRef(onSelect),inspect=useRef(onInspect)
  const lastGeometry=useRef(null)
  const [tileError,setTileError]=useState(false)
  const boundsRef=useRef(navigationBounds)
  choose.current=onSelect;inspect.current=onInspect;boundsRef.current=navigationBounds
  useEffect(()=>{
    const view=L.map(container.current,{scrollWheelZoom:false,zoomSnap:0.25}).setView([15.1,76.1],6)
    // Open on Karnataka rather than a fixed southern-India view; selections and bounds refine it later.
    view.fitBounds(L.geoJSON(boundary).getBounds(),{padding:[10,10],maxZoom:7,animate:false})
    map.current=view;layers.current=L.layerGroup().addTo(view)
    view.on('click',e=>choose.current?.({latitude:e.latlng.lat,longitude:((e.latlng.lng+180)%360+360)%360-180}))
    // The map may be portalled into a stage that is sized after mount: fit Karnataka again unless
    // points or district bounds have already taken over the view.
    const settle=setTimeout(()=>{if(map.current===view&&!boundsRef.current&&(!lastGeometry.current||lastGeometry.current.startsWith('[[]'))){view.invalidateSize?.();view.fitBounds(L.geoJSON(boundary).getBounds(),{padding:[10,10],maxZoom:7,animate:false})}},250)
    return ()=>{clearTimeout(settle);view.remove();map.current=null;layers.current=null;lastGeometry.current=null}
  },[])
  useEffect(()=>{
    if(!map.current)return
    const view=map.current,controller=new AbortController();let layer=null,active=true
    setTileError(false)
    if(mode==='street')layer=addBasemap(L,view,()=>{if(active)setTileError(true)})
    else {
      const timer=setTimeout(()=>controller.abort(),10000)
      ;(async()=>{try{
        const response=await fetch(tileMetadataURL(mode,providerSettings),{signal:controller.signal,credentials:'omit',referrerPolicy:'origin'})
        if(!response.ok)throw Error('Imagery unavailable')
        const metadata=validatedTileMetadata(await response.json())
        if(active){layer=L.tileLayer(metadata.url,{maxZoom:metadata.maxZoom,attribution:metadata.attribution,referrerPolicy:'origin',updateWhenIdle:true,keepBuffer:1}).addTo(view);layer.on('tileerror',()=>{if(active){view.removeLayer(layer);setTileError(true)}})}
      }catch{if(active)setTileError(true)}finally{clearTimeout(timer)}})()
    }
    return()=>{active=false;controller.abort();if(layer&&map.current===view)view.removeLayer(layer)}
  },[mode,providerSettings])
  useEffect(()=>{
    if(!map.current)return
    layers.current.clearLayers();const bounds=[]
    if(route?.coordinates?.length>1){const line=route.coordinates.map(([lon,lat])=>[lat,lon]);L.polyline(line,{color:'#1565c0',weight:5,opacity:.85}).addTo(layers.current);bounds.push(...line)}
    if(origin){L.circleMarker([origin.latitude,origin.longitude],{radius:5,color:'#365f7e'}).addTo(layers.current);bounds.push([origin.latitude,origin.longitude])}
    for(const point of points){
      const text=document.createElement('span');text.textContent=point.name
      // Numbered pins (label is the list position, digits only) link the map to the shelter list.
      const marker=point.label&&L.divIcon&&L.marker?L.marker([point.latitude,point.longitude],{icon:L.divIcon({className:'shelter-pin '+(point.tone==='limited'?'limited':'ok'),html:'<div class="shelter-pin-shape"><span>'+String(point.label).replace(/\D/g,'')+'</span></div>',iconSize:[30,30],iconAnchor:[15,30],tooltipAnchor:[0,-26]}),keyboard:true,title:point.name}):L.circleMarker([point.latitude,point.longitude],{radius:8,color:'#1b625d'})
      marker.bindTooltip(text).on('click',()=>inspect.current?.(point)).addTo(layers.current);bounds.push([point.latitude,point.longitude])
    }
    const geometry=JSON.stringify([bounds,inspection])
    if(geometry!==lastGeometry.current){
      lastGeometry.current=geometry
      if(bounds.length===1)map.current.setView(bounds[0],inspection?Math.max(16,map.current.getZoom?.()||16):13,{animate:false})
      else if(bounds.length)map.current.fitBounds(bounds,{paddingTopLeft:[20,40],paddingBottomRight:[20,20],maxZoom:inspection?18:14,animate:false})
    }
  },[points,origin,inspection,route])
  useEffect(()=>{if(focus&&map.current)map.current.setView([focus.latitude,focus.longitude],15,{animate:true})},[focus?.id,focus?.latitude,focus?.longitude])
  useEffect(()=>{if(navigationBounds&&map.current)map.current.fitBounds(navigationBounds,{padding:[20,20],animate:false})},[navigationBounds])
  useMapResize(map)
  return <><div ref={container} className="shelter-map" role="region" aria-label={label} />{tileError&&<p className="notice" role="status">{BASEMAP_NOTICE}</p>}</>
}
