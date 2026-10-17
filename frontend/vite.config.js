import { defineConfig } from 'vite'

const apiTarget = process.env.FLOODPULSE_API_TARGET || 'http://127.0.0.1:8000'
// Extra Host names the dev server accepts (e.g. ".trycloudflare.com" for a temporary phone-test tunnel).
// Empty by default, so only localhost/IP access is allowed unless explicitly enabled.
const allowedHosts = (process.env.FLOODPULSE_ALLOWED_HOSTS || '').split(',').map(h => h.trim()).filter(Boolean)
const securityHeaders = { 'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin' }

export default defineConfig({
  server: { proxy: { '/api': apiTarget }, headers: securityHeaders, ...(allowedHosts.length ? { allowedHosts } : {}) },
  preview: { proxy: { '/api': apiTarget }, headers: securityHeaders },
})
