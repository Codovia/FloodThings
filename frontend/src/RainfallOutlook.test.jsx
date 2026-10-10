import React from 'react'
import { afterEach,beforeEach,expect,it,vi } from 'vitest'
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import RainfallOutlook from './RainfallOutlook.jsx'

const kundapur={name:'Kundapur',latitude:13.6250993,longitude:74.6915722}
const mangaluru={name:'Mangaluru',latitude:12.8698101,longitude:74.8430082}
const weather={retrieved_at:'2026-10-09T13:30:00Z'}
const result=point=>({status:'available',experimental:true,location:point,model_version:'rainfall_logistic_v1',model_sha256:'a'.repeat(64),
 prediction:'below_heavy_threshold_predicted',prediction_text:'Below 64.5 mm predicted by the experimental model',probability:null,
 retrieved_at:weather.retrieved_at,feature_valid_through_utc:'2026-10-09T13:00:00Z',provider_grid:{latitude:13.6,longitude:74.7},
 horizon:{hours:24,start_utc:'2026-10-09T14:00:00Z',end_utc:'2026-10-10T14:00:00Z'},
 target:{threshold_mm:64.5,definition_url:'https://www.imdpune.gov.in/hazardatlas/extr_rainfallnew_p2001_2010.html'},
 validation:{model_type:'Logistic Regression',precision:88/607,recall:88/96,samples:2888}})
const reply=(data,ok=true)=>Promise.resolve({ok,json:async()=>data})
const run=()=>fireEvent.click(screen.getByRole('button',{name:'Run experimental rainfall model'}))
beforeEach(()=>{vi.stubGlobal('fetch',vi.fn(url=>reply(result(url.includes('12.8698101')?mangaluru:kundapur))))})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()})

it('loads on demand, renders trained model/target/window and no probability or flood prediction',async()=>{
 render(<RainfallOutlook point={kundapur} weather={weather} freshness="fresh" />)
 expect(fetch).not.toHaveBeenCalled();run()
 await screen.findByText('Below 64.5 mm predicted by the experimental model')
 expect(fetch).toHaveBeenCalledTimes(1)
 expect(fetch.mock.calls[0][0]).toBe('/api/ai/rainfall-outlook?latitude=13.6250993&longitude=74.6915722')
 expect(screen.getByText(/Model rainfall_logistic_v1/)).toBeTruthy()
 expect(screen.getByText(/ERA5 reanalysis-trained/)).toBeTruthy()
 expect(screen.getByText(/Below the threshold does not mean dry or safe/)).toBeTruthy()
 expect(screen.getByText(/not flood probability or an official warning/)).toBeTruthy()
 expect(screen.getByText(/Target: heavy rainfall ≥64.5 mm in 24 hours/)).toBeTruthy()
 expect(screen.getByText(/precision: 14.50% · recall: 91.67%/)).toBeTruthy()
 expect(screen.getByText(/Not validated for automatic emergency warnings/)).toBeTruthy()
})

it.each([undefined,{model_type:'Logistic Regression',precision:NaN,recall:1,samples:2888}])('does not fabricate missing or invalid validation metrics',async(validation)=>{
 fetch.mockImplementation(()=>reply({...result(kundapur),validation}))
 render(<RainfallOutlook point={kundapur} weather={weather} freshness="fresh" />);run()
 await screen.findByText('Below 64.5 mm predicted by the experimental model')
 expect(screen.getByText(/Held-out metrics unavailable/)).toBeTruthy()
 expect(screen.queryByText(/precision: 14.50%/)).toBeNull()
})

it('stale weather explicitly labels previously retrieved outlook',async()=>{
 render(<RainfallOutlook point={kundapur} weather={weather} freshness="stale" />);run()
 await screen.findByText('Below 64.5 mm predicted by the experimental model')
 expect(screen.getByText(/Weather is stale or refreshing/)).toBeTruthy()
})

it('new weather receipt reruns hourly inference once without a seven-day weather fetch',async()=>{
 const {rerender}=render(<RainfallOutlook point={kundapur} weather={weather} freshness="fresh" />);run()
 await screen.findByText('Below 64.5 mm predicted by the experimental model')
 rerender(<RainfallOutlook point={{...kundapur}} weather={{...weather}} freshness="fresh" />)
 expect(fetch).toHaveBeenCalledTimes(1)
 rerender(<RainfallOutlook point={kundapur} weather={{retrieved_at:'2026-10-09T19:30:00Z'}} freshness="fresh" />)
 await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2))
 expect(fetch.mock.calls.every(([url])=>url.startsWith('/api/ai/'))).toBe(true)
})

it('location switching aborts and suppresses the older prediction',async()=>{
 let finish
 fetch.mockImplementation(url=>url.includes('13.6250993')?new Promise(resolve=>{finish=resolve}):reply(result(mangaluru)))
 const {rerender}=render(<RainfallOutlook point={kundapur} weather={weather} freshness="fresh" />);run()
 const signal=fetch.mock.calls[0][1].signal
 rerender(<RainfallOutlook point={mangaluru} weather={weather} freshness="fresh" />)
 await screen.findByText('Below 64.5 mm predicted by the experimental model');expect(signal.aborted).toBe(true)
 await act(async()=>finish({ok:true,json:async()=>({...result(kundapur),prediction:'heavy_rainfall_predicted',prediction_text:'OLD PREDICTION'})}))
 expect(screen.queryByText('OLD PREDICTION')).toBeNull()
 expect(screen.getByText(/Mangaluru · next 24/)).toBeTruthy()
})

it('provider failure clears prior prediction and offers manual retry',async()=>{
 render(<RainfallOutlook point={kundapur} weather={weather} freshness="fresh" />);run()
 await screen.findByText('Below 64.5 mm predicted by the experimental model')
 fetch.mockImplementation(()=>reply({status:'unavailable',message:'Controlled provider failure',prediction:null},false))
 fireEvent.click(screen.getByRole('button',{name:'Retry rainfall outlook'}))
 expect((await screen.findByRole('alert',{name:'AI rainfall outlook error'})).textContent).toContain('Controlled provider failure')
 expect(screen.queryByText('Below 64.5 mm predicted by the experimental model')).toBeNull()
})

it('missing weather receipt does not request model inputs',()=>{
 render(<RainfallOutlook point={kundapur} weather={null} freshness="unavailable" />);run()
 expect(screen.getByText(/Usable weather retrieval is required/)).toBeTruthy();expect(fetch).not.toHaveBeenCalled()
})

it.each(['wrong_location','probability','target','window','missing_time','grid'])('rejects incompatible inference response: %s',async(kind)=>{
 const data=result(kundapur)
 if(kind==='wrong_location')data.location=mangaluru
 if(kind==='probability')data.probability=0.6
 if(kind==='target')data.target.threshold_mm=50
 if(kind==='window')data.horizon.end_utc='2026-10-11T14:00:00Z'
 if(kind==='missing_time')data.feature_valid_through_utc=null
 if(kind==='grid')data.provider_grid.latitude=100
 fetch.mockImplementation(()=>reply(data))
 render(<RainfallOutlook point={kundapur} weather={weather} freshness="fresh" />);run()
 expect((await screen.findByRole('alert')).textContent).toContain('does not match')
 expect(screen.queryByText('Below 64.5 mm predicted by the experimental model')).toBeNull()
})

it('timeout/unmount cleans up the request without rapid retry loops',async()=>{
 vi.useFakeTimers();fetch.mockImplementation((url,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))))
 const {unmount}=render(<RainfallOutlook point={kundapur} weather={weather} freshness="fresh" />);run()
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000)})
 expect(screen.getByRole('alert').textContent).toContain('timed out')
 await act(async()=>{await vi.advanceTimersByTimeAsync(60000)})
 expect(fetch).toHaveBeenCalledTimes(1);unmount();expect(vi.getTimerCount()).toBe(0)
})
