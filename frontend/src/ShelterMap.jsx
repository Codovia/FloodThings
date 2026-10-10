import React,{useEffect,useRef,useState} from 'react'
import L from 'leaflet'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import {tileMetadataURL,validatedTileMetadata} from './adminMapProvider.js'
import useMapResize from './useMapResize.js'
import 'leaflet/dist/leaflet.css'

export default function ShelterMap({points=[],origin=null,onSelect=null,label='Shelter entrance map',mode='street',providerSettings=null,inspection=false}) {
  const container=useRef(null),map=useRef(null),layers=useRef(null),choose=useRef(onSelect)
  const [tileError,setTileError]=useState(false)
  choose.current=onSelect
  useEffect(()=>{
    const view=L.map(container.current,{scrollWheelZoom:false}).setView([15.1,76.1],6)
    map.current=view;layers.current=L.layerGroup().addTo(view)
    view.on('click',e=>choose.current?.({latitude:e.latlng.lat,longitude:((e.latlng.lng+180)%360+360)%360-180}))
    return ()=>{view.remove();map.current=null;layers.current=null}
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
    if(origin){L.circleMarker([origin.latitude,origin.longitude],{radius:5,color:'#365f7e'}).addTo(layers.current);bounds.push([origin.latitude,origin.longitude])}
    for(const point of points){
      const text=document.createElement('span');text.textContent=point.name
      L.circleMarker([point.latitude,point.longitude],{radius:8,color:'#1b625d'}).bindTooltip(text).addTo(layers.current);bounds.push([point.latitude,point.longitude])
    }
    if(bounds.length===1)map.current.setView(bounds[0],inspection?Math.max(16,map.current.getZoom?.()||16):13,{animate:false})
    else if(bounds.length)map.current.fitBounds(bounds,{padding:[20,20],maxZoom:inspection?18:14,animate:false})
  },[points,origin,inspection])
  useMapResize(map)
  return <><div ref={container} className="shelter-map" role="region" aria-label={label} />{tileError&&<p className="notice" role="status">{BASEMAP_NOTICE}</p>}</>
}
