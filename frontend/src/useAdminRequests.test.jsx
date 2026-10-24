import {afterEach,expect,it,vi} from 'vitest'
import {act,cleanup,renderHook} from '@testing-library/react'
import useAdminRequests from './useAdminRequests.js'
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.useRealTimers()})
it('bounds an uncooperative request and preserves uncertain-write semantics',async()=>{
 vi.useFakeTimers();vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})))
 const {result,unmount}=renderHook(()=>useAdminRequests(vi.fn()))
 let outcome;act(()=>{outcome=result.current.request('/api/admin/shelters',{method:'POST'}).catch(e=>e.message)})
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000)})
 expect(await outcome).toContain('A write may have completed');expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
 unmount();expect(vi.getTimerCount()).toBe(0)
})
it('401 clears private state, aborts other calls and never exposes a late success',async()=>{
 let finish;vi.stubGlobal('fetch',vi.fn(url=>url==='late'?new Promise(resolve=>{finish=resolve}):Promise.resolve({ok:false,status:401,json:async()=>({detail:'Session expired'})})))
 const expired=vi.fn(),{result}=renderHook(()=>useAdminRequests(expired))
 let late,denied;act(()=>{late=result.current.request('late').catch(e=>e.name);denied=result.current.request('denied').catch(e=>e.status)})
 await act(async()=>{await denied});expect(await denied).toBe(401);expect(expired).toHaveBeenCalledTimes(1);expect(await late).toBe('AbortError')
 await act(async()=>finish({ok:true,json:async()=>({private:'ISOLATED TEST'})}));expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
})
it('unmount cancels pending calls and their timers',async()=>{
 vi.useFakeTimers();vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})));const {result,unmount}=renderHook(()=>useAdminRequests(vi.fn()))
 let promise;act(()=>{promise=result.current.request('/api/admin/session').catch(e=>e.name)})
 unmount();expect(await promise).toBe('AbortError');expect(vi.getTimerCount()).toBe(0)
})
