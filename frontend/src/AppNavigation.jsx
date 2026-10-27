import React, { useCallback, useEffect, useRef, useState } from 'react'

export const PAGES = [
  {path:'/',name:'Home',icon:'home'},
  {path:'/flood-map',name:'Flood Map',icon:'map'}, {path:'/shelters',name:'Shelters',icon:'shelter'},
  {path:'/report',name:'Report an incident',icon:'report'}, {path:'/alerts',name:'Telegram alerts',icon:'alert'},
  {path:'/how-it-works',name:'How it works',icon:'info'},
  {path:'/model-performance',name:'Model performance',icon:'chart'},
  {path:'/admin',name:'Admin',icon:'admin'},
]
// The Weather page was merged into Home; old /weather links open Home.
const currentPath=()=>{
 const path=window.location.pathname.replace(/\/+$/, '') || '/'
 if(path!=='/weather')return path
 window.history.replaceState(null,'','/'+window.location.search+window.location.hash)
 return '/'
}
export function usePage(){
 const [path,setPath]=useState(currentPath)
 const heading=useRef(null)
 const navigate=useCallback(next=>{if(currentPath()!==next){window.history.pushState(null,'',next);setPath(next)}},[])
 useEffect(()=>{const pop=()=>setPath(currentPath());window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[])
 useEffect(()=>{document.title=`${PAGES.find(p=>p.path===path)?.name || 'Page unavailable'} · FloodPulse`;heading.current?.focus({preventScroll:true});window.scrollTo?.({top:0,behavior:'instant'})},[path])
 return {path,navigate,heading}
}
export function PageLink({to,navigate,children,onClick,...props}){
 return <a href={to} {...props} onClick={event=>{if(!event.defaultPrevented && event.button===0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey){event.preventDefault();onClick?.(event);navigate(to)}else{onClick?.(event)}}}>{children}</a>
}
export function Icon({name}){
 const paths={chart:'M4 20h16M7 16v-5m5 5V7m5 9v-3',report:'M5 3h14v18H5V3Zm4 5h6m-6 4h6m-6 4h3',info:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-11v6m0-9h.01',alert:'M12 3a6 6 0 0 0-6 6v5l-2 3h16l-2-3V9a6 6 0 0 0-6-6Zm-2 17h4',home:'m3 10 9-7 9 7M5 9v12h14V9M9 21v-7h6v7',weather:'M7 17a4 4 0 1 1 1-8 5 5 0 0 1 9 2 3 3 0 0 1 0 6H7Zm4 3-1 2m7-2-1 2M4 3v2M1 7h2',map:'m2 5 6-3 8 3 6-3v17l-6 3-8-3-6 3V5Zm6-3v17m8-14v17',shelter:'m2 11 10-8 10 8M4 10v11h16V10M9 21v-7h6v7M10 9h4',admin:'m12 2 9 4v6c0 5-5 8-9 10-4-2-9-5-9-10V6l9-4Zm-3 10 2 2 4-5',water:'M12 2S4 11 4 16a8 8 0 0 0 16 0c0-5-8-14-8-14ZM8 16c0 2 2 4 4 4'}
 return <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name] || paths.water}/></svg>
}
export function AppHeader({path,navigate,mode=null}){
 const [expanded,setExpanded]=useState(false)
 const toggle=useRef(null)
 useEffect(()=>setExpanded(false),[path])
 function escape(event){if(event.key==='Escape' && expanded){setExpanded(false);toggle.current?.focus()}}
 return <><a className="skip-link" href="#page-content">Skip to page content</a><header className="app-header" onKeyDown={escape}>
 <div className="header-inner"><PageLink to="/" navigate={navigate} className="app-brand" aria-label="FloodPulse Home"><span className="brand-mark"><Icon name="water"/></span><span><strong>FloodPulse{mode==='demonstration'&&<span className="demo-environment-badge">DEMO ONLY</span>}</strong><small>Local information & emergency response</small></span></PageLink>
 <button ref={toggle} className="nav-toggle" type="button" aria-label={expanded?'Close navigation menu':'Open navigation menu'} aria-expanded={expanded} aria-controls="primary-navigation" onClick={()=>setExpanded(v=>!v)}>{expanded?'Close':'Menu'}<span aria-hidden="true">{expanded?'×':'☰'}</span></button>
 <nav id="primary-navigation" className={expanded?'primary-nav expanded':'primary-nav'} aria-label="Main navigation">{PAGES.filter(page=>!page.hidden).map(page=><PageLink key={page.path} to={page.path} navigate={navigate} onClick={()=>setExpanded(false)} aria-current={path===page.path?'page':undefined}><Icon name={page.icon}/>{page.name}</PageLink>)}</nav>
 </div></header></>
}
// Phones: the four main tasks stay visible at the bottom, within thumb reach (visible navigation is easier to
// find than a hidden menu; Android recommends 3–5 destinations). "Menu" in the header keeps every page.
const QUICK_PAGES=[{path:'/',name:'Home',icon:'home'},{path:'/flood-map',name:'Map',icon:'map'},{path:'/report',name:'Report',icon:'report'},{path:'/shelters',name:'Shelters',icon:'shelter'}]
export function BottomNav({path,navigate}){
 return <nav className="bottom-nav" aria-label="Quick navigation">{QUICK_PAGES.map(page=><PageLink key={page.path} to={page.path} navigate={navigate} aria-current={path===page.path?'page':undefined}><Icon name={page.icon}/><span>{page.name}</span></PageLink>)}</nav>
}

