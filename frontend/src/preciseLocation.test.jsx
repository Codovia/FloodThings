import {afterEach,expect,it,vi} from 'vitest'
import {preciseLocation} from './preciseLocation.js'
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals()})
const fix=accuracy=>({coords:{latitude:13.34,longitude:74.74,accuracy},timestamp:Date.now()})
it('waits for the person to answer the permission prompt; the 20 s improvement window starts at the first fix',async()=>{
 vi.useFakeTimers();let report;const clearWatch=vi.fn()
 vi.stubGlobal('navigator',{geolocation:{watchPosition:ok=>{report=ok;return 3},clearWatch}})
 let result=null;preciseLocation().then(r=>{result=r},e=>{result=e})
 await vi.advanceTimersByTimeAsync(45000);expect(result).toBeNull()   // still waiting at 45 s (prompt not yet answered)
 report(fix(300));await vi.advanceTimersByTimeAsync(19000);expect(result).toBeNull()
 await vi.advanceTimersByTimeAsync(1500);expect(result.coords.accuracy).toBe(300);expect(clearWatch).toHaveBeenCalledWith(3)
})
it('gives up after 60 s without any fix and reports a timeout',async()=>{
 vi.useFakeTimers();vi.stubGlobal('navigator',{geolocation:{watchPosition:()=>4,clearWatch:vi.fn()}})
 let error=null;preciseLocation().catch(e=>{error=e})
 await vi.advanceTimersByTimeAsync(60500);expect(error.code).toBe(3)
})
