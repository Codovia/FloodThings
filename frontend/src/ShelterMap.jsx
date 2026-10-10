import React,{useEffect,useRef} from 'react'
import L from 'leaflet'
import useMapResize from './useMapResize.js'
import 'leaflet/dist/leaflet.css'

export default function ShelterMap({points=[],origin=null,onSelect=null,label='Shelter entrance map'}) {
  const container=useRef(null),map=useRef(null),layers=useRef(null),choose=useRef(onSelect)
  choose.current=onSelect
  useEffect(()=>{
    const view=L.map(container.current,{scrollWheelZoom:false}).setView([15.1,76.1],6)
    map.current=view;layers.current=L.layerGroup().addTo(view)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(view)
    view.on('click',e=>choose.current?.({latitude:e.latlng.lat,longitude:((e.latlng.lng+180)%360+360)%360-180}))
    return ()=>{view.remove();map.current=null;layers.current=null}
  },[])
  useEffect(()=>{
    if(!map.current)return
    layers.current.clearLayers();const bounds=[]
    if(origin){L.circleMarker([origin.latitude,origin.longitude],{radius:5,color:'#365f7e'}).addTo(layers.current);bounds.push([origin.latitude,origin.longitude])}
    for(const point of points){
      const text=document.createElement('span');text.textContent=point.name
      L.circleMarker([point.latitude,point.longitude],{radius:8,color:'#1b625d'}).bindTooltip(text).addTo(layers.current);bounds.push([point.latitude,point.longitude])
    }
    if(bounds.length===1)map.current.setView(bounds[0],13,{animate:false})
    else if(bounds.length)map.current.fitBounds(bounds,{padding:[20,20],maxZoom:14,animate:false})
  },[points,origin])
  useMapResize(map)
  return <div ref={container} className="shelter-map" role="region" aria-label={label} />
}
