import React from 'react'
import {afterEach,expect,it,vi} from 'vitest'
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import AdminEntranceMap from './AdminEntranceMap.jsx'
const state=vi.hoisted(()=>({enabled:false,props:null}))
vi.mock('./adminMapProvider.js',async original=>({...await original(),adminMapSettings:()=>({get enabled(){return state.enabled},publicKey:'ISOLATED_PUBLIC_BROWSER_KEY'})}))
vi.mock('./ShelterMap.jsx',()=>({default:props=>{state.props=props;return <button onClick={()=>props.onSelect({latitude:13.5,longitude:74.7})}>TEST ONLY entrance click</button>}}))
vi.mock('./LocationDirectorySelector.jsx',()=>({default:props=><button onClick={()=>props.onChoose({name:'Verified locality reference',latitude:13.5,longitude:74.7})}>TEST ONLY locality reference</button>}))
afterEach(()=>{cleanup();vi.unstubAllGlobals();state.enabled=false})
it('unconfigured imagery and building search remain disabled; street and verified place navigation work',()=>{
 const select=vi.fn();render(<AdminEntranceMap entrance={[]} onSelect={select}/>);expect(screen.getByRole('option',{name:'Satellite imagery'}).disabled).toBe(true);expect(screen.getByRole('option',{name:'Satellite Hybrid'}).disabled).toBe(true);expect(screen.getByLabelText('Search place or building name').disabled).toBe(true)
 fireEvent.click(screen.getByText('TEST ONLY locality reference'));expect(state.props.origin.name).toBe('Verified locality reference');expect(select).not.toHaveBeenCalled();fireEvent.click(screen.getByText('TEST ONLY entrance click'));expect(select).toHaveBeenCalledWith({latitude:13.5,longitude:74.7})
})
it('authorized building search navigates a reference and never automatically assigns the shelter',async()=>{
 state.enabled=true;const select=vi.fn();vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({type:'FeatureCollection',features:[{id:'fixture',place_name:'TEST ONLY BUILDING',geometry:{type:'Point',coordinates:[74.7,13.5]}}]})})))
 render(<AdminEntranceMap entrance={[]} onSelect={select}/>);fireEvent.change(screen.getByLabelText('Search place or building name'),{target:{value:'TEST BUILDING'}});expect(fetch).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Search building references'}));fireEvent.click(await screen.findByRole('button',{name:'TEST ONLY BUILDING — inspect reference point'}));expect(state.props.origin.name).toBe('TEST ONLY BUILDING');expect(state.props.points).toEqual([]);expect(select).not.toHaveBeenCalled();fireEvent.change(screen.getByLabelText('Map mode'),{target:{value:'hybrid'}});expect(state.props.mode).toBe('hybrid')
})
it('provider failure yields no invented search results',async()=>{
 state.enabled=true;vi.stubGlobal('fetch',vi.fn(async()=>({ok:false})));render(<AdminEntranceMap entrance={[]} onSelect={vi.fn()}/>);fireEvent.change(screen.getByLabelText('Search place or building name'),{target:{value:'TEST BUILDING'}});fireEvent.click(screen.getByRole('button',{name:'Search building references'}));await waitFor(()=>expect(screen.getByRole('alert')).toBeTruthy());expect(screen.queryByRole('list',{name:'Building reference results'})).toBeNull()
})
