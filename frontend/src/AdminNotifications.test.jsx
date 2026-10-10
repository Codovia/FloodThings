import React from 'react'
import { beforeEach, afterEach, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, act, within } from '@testing-library/react'
import AdminNotifications from './AdminNotifications'

const session={user:{id:'isolated'},mode:'demonstration',csrf_token:'ISOLATED'}
const config={configured:true,destinations:[{id:'test',label:'Private test',test_only:true}],shelters:[]}
const row={id:'notice-id',destination_label:'Private test',kind:'informational',text:'Exact server preview — TEST ONLY',content_sha256:'a'.repeat(64),created_by:'isolated',status:'draft'}
let request, records, calls, outcome
beforeEach(()=>{
 records=[];calls=[];outcome='accepted'
 request=vi.fn(async(path,options={})=>{
  if(path.endsWith('/options'))return config
  if(path.includes('?'))return {notifications:records,total:records.length}
  const body=JSON.parse(options.body);calls.push({path,body})
  if(path.endsWith('/send')){records=[{...row,status:outcome}];return records[0]}
  records=[row];return row
 })
})
afterEach(()=>{cleanup();vi.useRealTimers()})
async function mount(){render(<AdminNotifications session={session} request={request} />);await screen.findByText('No notification attempts or previews recorded.')}
async function review(){fireEvent.change(screen.getByLabelText('Telegram destination'),{target:{value:'test'}});fireEvent.change(screen.getByLabelText('Notification message'),{target:{value:'Isolated test notice'}});fireEvent.click(screen.getByRole('button',{name:'Review exact notification'}));await screen.findByRole('heading',{name:'Exact message preview — Private test'})}
function approve(){fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Approve and send once through Telegram'}))}

it('requires server preview and explicit approval with the reviewed digest',async()=>{
 await mount();await review();expect(calls).toHaveLength(1);expect(calls[0].body.destination_id).toBe('test');expect(calls[0].body.request_id).toBeTruthy()
 expect(screen.getByRole('button',{name:'Approve and send once through Telegram'}).disabled).toBe(true)
 expect(within(screen.getByLabelText('Notification preview')).getByText(row.text)).toBeTruthy()
 approve();await screen.findAllByText(/Telegram accepted the message/)
 expect(calls[1].body).toEqual({approve:true,content_sha256:'a'.repeat(64)});expect(calls).toHaveLength(2)
 expect(screen.queryByRole('button',{name:'Approve and send once through Telegram'})).toBeNull()
 expect(screen.getAllByText(/Recipient reading is not confirmed/).length).toBeGreaterThan(0)
})
it('changing content clears approval and invalidates the preview',async()=>{
 await mount();await review();fireEvent.click(screen.getByRole('checkbox'));fireEvent.change(screen.getByLabelText('Notification message'),{target:{value:'Different notice'}})
 expect(screen.queryByLabelText('Notification preview')).toBeNull();expect(calls).toHaveLength(1)
})
it('missing configuration disables messaging without fabricated results',async()=>{
 request.mockImplementation(async path=>path.endsWith('/options')?{configured:false,reason:'Telegram not configured',destinations:[],shelters:[]}:{notifications:[],total:0})
 await mount();expect(screen.getByText(/Telegram not configured/)).toBeTruthy();expect(screen.getByRole('button',{name:'Review exact notification'}).disabled).toBe(true)
 expect(screen.queryByRole('checkbox')).toBeNull()
})
it.each(['rejected','delivery_unknown'])('shows accurate %s status without automatic retries',async status=>{
 outcome=status;await mount();await review();approve();await screen.findAllByText(status==='rejected'?/Telegram rejected/:/Delivery is uncertain/)
 expect(calls).toHaveLength(2);fireEvent.click(screen.getByRole('button',{name:'Refresh notification history'}));await act(async()=>{});expect(calls).toHaveLength(2)
})
it('prevents duplicate clicks while an approval request is pending',async()=>{
 let finish;await mount();await review();request.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 fireEvent.click(screen.getByRole('checkbox'));const button=screen.getByRole('button',{name:'Approve and send once through Telegram'});fireEvent.click(button);fireEvent.click(button)
 expect(screen.queryByRole('checkbox')).toBeNull();await act(async()=>finish({...row,status:'accepted'}));expect(screen.queryByRole('button',{name:'Approve and send once through Telegram'})).toBeNull()
})
it('a lost send response leaves uncertain state and no repeat-send button',async()=>{
 await mount();await review();request.mockImplementationOnce(async()=>{throw Error('Controlled transport failure')});approve()
 await screen.findByText('Controlled transport failure');expect(screen.getByText(/outcome not recorded/)).toBeTruthy();expect(screen.queryByRole('button',{name:'Approve and send once through Telegram'})).toBeNull()
})
it('supports verified shelter selection and independent emergency composition',async()=>{
 request.mockImplementation(async(path,options={})=>{
  if(path.endsWith('/options'))return {...config,shelters:[{id:'shelter',name:'DEMONSTRATION ONLY',district_name:'Udupi'}]}
  if(path.includes('?'))return {notifications:[],total:0}
  calls.push(JSON.parse(options.body));return row
 })
 await mount();fireEvent.change(screen.getByLabelText('Notification type'),{target:{value:'emergency'}});fireEvent.change(screen.getByLabelText('Include currently verified Open shelter'),{target:{value:'shelter'}});await review()
 expect(calls[0].shelter_id).toBe('shelter');expect(calls[0].kind).toBe('emergency');expect(screen.getByText(/Experimental rainfall outputs never trigger/)).toBeTruthy()
})
it('cleans up pending requests and timers on unmount',async()=>{
 vi.useFakeTimers();const signals=[];request.mockImplementation((path,settings)=>{signals.push(settings.signal);return new Promise(()=>{})})
 const {unmount}=render(<AdminNotifications session={session} request={request} />);expect(signals).toHaveLength(2);unmount();expect(signals.every(s=>s.aborted)).toBe(true)
 // Abort-aware fetch settles call() and clears its timer; emulate it in a second render.
 request.mockImplementation((path,settings)=>new Promise((resolve,reject)=>settings.signal.addEventListener('abort',()=>reject(Object.assign(Error(),{name:'AbortError'})))))
 const second=render(<AdminNotifications session={session} request={request} />);await act(async()=>second.unmount());await act(async()=>vi.runAllTimersAsync());expect(vi.getTimerCount()).toBe(0)
})
