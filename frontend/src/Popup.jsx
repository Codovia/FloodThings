import React, { useEffect, useId, useRef, useState } from 'react'

// A button that opens details in a centred dialog instead of expanding the page (one-screen rule).
// Escape or "Close" returns focus to the button. The dialog body must itself fit the screen;
// long content inside it uses ScreenTabs. Pass `open` and `onClose` to open it from page logic (no button).
export default function Popup({ label, title, className = '', buttonClassName = 'link-button', children, open: controlled, onClose }) {
  const [own, setOwn] = useState(false)
  const isControlled = controlled !== undefined, open = isControlled ? controlled : own
  const setOpen = value => { if (isControlled) { if (!value) onClose?.() } else setOwn(value) }
  const button = useRef(null), dialog = useRef(null), id = useId().replace(/:/g, '')
  function close() { setOpen(false); button.current?.focus() }
  useEffect(() => {
    if (!open) return
    dialog.current?.focus()
    const key = event => { if (event.key === 'Escape') { event.stopPropagation(); close() } }
    document.addEventListener('keydown', key, true)
    return () => document.removeEventListener('keydown', key, true)
  }, [open])
  return <>
    {!isControlled && <button ref={button} type="button" className={buttonClassName} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>{label}</button>}
    {open && <div className="popup-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) close() }}>
      <div ref={dialog} className={`popup ${className}`} role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} tabIndex={-1}>
        <div className="popup-head"><h3 id={`${id}-title`}>{title}</h3><button type="button" className="secondary" onClick={close}>Close</button></div>
        <div className="popup-body">{typeof children === 'function' ? children(close) : children}</div>
      </div>
    </div>}
  </>
}
