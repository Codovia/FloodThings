import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './leafletHiddenMaps.js'
import './styles.css'

createRoot(document.getElementById('root')).render(<App />)

import './UserExperience.css'
// Loaded last: every page fits one screen with no scrolling (demo requirement, 20 Oct 2026).
import './OneScreen.css'
