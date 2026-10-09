import { defineConfig } from 'vite'

const apiTarget = process.env.FLOODPULSE_API_TARGET || 'http://127.0.0.1:8000'
const securityHeaders = { 'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin' }

export default defineConfig({
  server: { proxy: { '/api': apiTarget }, headers: securityHeaders },
  preview: { proxy: { '/api': apiTarget }, headers: securityHeaders },
})
