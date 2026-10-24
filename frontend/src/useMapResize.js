import { useEffect } from 'react'

// A persistent map may become visible again after navigation. Resize without
// moving its selected point or fitting a different geographic extent.
export default function useMapResize(map){
 useEffect(()=>{
  const element=map.current?.getContainer?.()
  if(!element || typeof ResizeObserver==='undefined')return
  const observer=new ResizeObserver(()=>{
   if(element.clientWidth>0 && element.clientHeight>0)map.current?.invalidateSize?.({pan:false})
  })
  observer.observe(element)
  return()=>observer.disconnect()
 },[map])
}
