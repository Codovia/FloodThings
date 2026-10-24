import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {MAX_BYTES,MAX_PIXELS,preparePhoto} from './reportPhoto.js'

let drawn,blobSize
beforeEach(()=>{
 drawn=null;blobSize=1000
 vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockImplementation(function(){const canvas=this;return {drawImage:(_,x,y,w,h)=>{drawn={w,h,canvasW:canvas.width,canvasH:canvas.height}}}})
 vi.spyOn(HTMLCanvasElement.prototype,'toBlob').mockImplementation(function(done,type,quality){done(new Blob([new Uint8Array(blobSize)],{type}))})
})
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals()})
const bitmap=(width,height)=>vi.stubGlobal('createImageBitmap',vi.fn(async()=>({width,height,close:vi.fn()})))
const file=(bytes,type='image/jpeg')=>new File([new Uint8Array(bytes)],'photo',{type})

it('keeps a photo that already fits, so its embedded metadata survives',async()=>{
 bitmap(3000,3000);const original=file(2*1024*1024)
 const ready=await preparePhoto(original)
 expect(ready).toMatchObject({resized:false,mime:'image/jpeg',width:3000,height:3000});expect(ready.blob).toBe(original);expect(drawn).toBeNull()
})
it('shrinks a 12-megapixel phone photo below the server limit as JPEG',async()=>{
 bitmap(4000,3000)
 const ready=await preparePhoto(file(3*1024*1024,'image/png'))
 expect(ready.resized).toBe(true);expect(ready.mime).toBe('image/jpeg');expect(ready.width*ready.height).toBeLessThanOrEqual(MAX_PIXELS)
 expect(drawn).toEqual({w:ready.width,h:ready.height,canvasW:ready.width,canvasH:ready.height})
})
it('shrinks a photo that is within the pixel limit but over 5 MiB',async()=>{
 bitmap(3000,3000)
 const ready=await preparePhoto(file(MAX_BYTES+1))
 expect(ready.resized).toBe(true);expect(ready.blob.size).toBeLessThanOrEqual(MAX_BYTES)
})
it('refuses unsupported types, unreadable images and photos that stay too large',async()=>{
 await expect(preparePhoto(file(10,'image/gif'))).rejects.toThrow('Choose a JPEG or PNG photo.')
 vi.stubGlobal('createImageBitmap',vi.fn(async()=>{throw Error('decode')}))
 await expect(preparePhoto(file(10))).rejects.toThrow('could not be opened')
 bitmap(4000,3000);blobSize=MAX_BYTES+1
 await expect(preparePhoto(file(10))).rejects.toThrow('too large even after shrinking')
})
