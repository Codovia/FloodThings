import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import AdminShelters from './AdminShelters.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(window.location.pathname.replace(/\/$/, '') === '/admin' ? <AdminShelters /> : <App />)
