import {afterEach,expect,it,vi} from 'vitest'
import {cleanup,renderHook} from '@testing-library/react'
import useMapResize from './useMapResize.js'
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('invalidates only visible map sizes and disconnects without recentering',()=>{let callback;const observe=vi.fn(),disconnect=vi.fn();vi.stubGlobal('ResizeObserver',class{constructor(fn){callback=fn}observe=observe;disconnect=disconnect});const element={clientWidth:0,clientHeight:0};const map={current:{getContainer:()=>element,invalidateSize:vi.fn(),setView:vi.fn()}};const {unmount}=renderHook(()=>useMapResize(map));expect(observe).toHaveBeenCalledWith(element);callback();expect(map.current.invalidateSize).not.toHaveBeenCalled();element.clientWidth=600;element.clientHeight=400;callback();expect(map.current.invalidateSize).toHaveBeenCalledWith({pan:false});expect(map.current.setView).not.toHaveBeenCalled();unmount();expect(disconnect).toHaveBeenCalledOnce()})
