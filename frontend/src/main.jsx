import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import ErrorBoundary, { reportError } from './ErrorBoundary.jsx'
import './leafletHiddenMaps.js'
import './styles.css'

// Errors outside React rendering (event handlers, promises) are reported too; the page keeps working.
window.addEventListener('error', event => reportError(event.error || event.message))
window.addEventListener('unhandledrejection', event => reportError(event.reason))
createRoot(document.getElementById('root')).render(<ErrorBoundary><App /></ErrorBoundary>)

import './UserExperience.css'
// Loaded last: every page fits one screen with no scrolling (demo requirement, 20 Oct 2026).
import './OneScreen.css'
