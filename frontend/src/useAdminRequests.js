import { useEffect, useRef } from 'react'

// Private requests share cancellation/generation guards, including responses
// that arrive after logout or whose mock/provider ignores AbortSignal.
export default function useAdminRequests(onUnauthorized) {
  const state = useRef({ mounted: true, generation: 0, controllers: new Set() })
  const unauthorized = useRef(onUnauthorized); unauthorized.current = onUnauthorized
  function cancel(except = null) {
    state.current.generation++
    for (const controller of state.current.controllers) if(controller !== except) controller.abort()
  }
  useEffect(() => {
    state.current.mounted = true
    return () => { state.current.mounted = false; cancel() }
  }, [])
  function current(generation) { return state.current.mounted && state.current.generation === generation }
  async function request(path, settings = {}) {
    const generation = state.current.generation, controller = new AbortController()
    const suppliedSignal = settings.signal
    const relay = () => controller.abort()
    suppliedSignal?.addEventListener('abort', relay, { once: true })
    if (suppliedSignal?.aborted) controller.abort()
    state.current.controllers.add(controller)
    let timeout = false, abortListener
    const timer = setTimeout(() => { timeout = true; controller.abort() }, 15000)
    try {
      const aborted = new Promise((_, reject) => {
        abortListener = () => reject(new DOMException('Aborted', 'AbortError'))
        controller.signal.addEventListener('abort', abortListener, { once: true })
        if (controller.signal.aborted) abortListener()
      })
      const result = (async () => {
        const response = await fetch(path, { ...settings, signal: controller.signal })
        const data = await response.json()
        if (!current(generation) || controller.signal.aborted) throw new DOMException('Aborted', 'AbortError')
        if (!response.ok) {
          if (response.status === 401) { cancel(controller); unauthorized.current() }
          const error = Error(typeof data.detail === 'string' ? data.detail : 'Invalid shelter request; check fields and verification confirmations')
          error.status = response.status
          throw error
        }
        return data
      })()
      return await Promise.race([result, aborted])
    } catch (error) {
      if (timeout) throw Error('Administrator request timed out. A write may have completed; refresh assignments or history before retrying.')
      throw error
    } finally {
      clearTimeout(timer)
      suppliedSignal?.removeEventListener('abort', relay)
      controller.signal.removeEventListener('abort', abortListener)
      state.current.controllers.delete(controller)
    }
  }
  return { request, cancel, generation: () => state.current.generation, current, mounted: () => state.current.mounted }
}
