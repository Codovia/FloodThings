import fs from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vite'

const apiTarget = process.env.FLOODPULSE_API_TARGET || 'http://127.0.0.1:8000'
// Extra Host names the dev server accepts (e.g. ".trycloudflare.com" for a temporary phone-test tunnel).
// Empty by default, so only localhost/IP access is allowed unless explicitly enabled.
const allowedHosts = (process.env.FLOODPULSE_ALLOWED_HOSTS || '').split(',').map(h => h.trim()).filter(Boolean)
const securityHeaders = { 'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin' }
// ./floodpulse.sh --lan: HTTPS with the laptop's local certificate (scripts/lan_tls.py). Devices download the
// certificate authority (public part only) once from /floodpulse-local-ca.crt and trust it.
const tlsDir = process.env.FLOODPULSE_TLS_DIR
const https = tlsDir ? { key: fs.readFileSync(path.join(tlsDir, 'lan.key')), cert: fs.readFileSync(path.join(tlsDir, 'lan.crt')) } : null
const localCertificate = {
  name: 'floodpulse-local-certificate',
  configureServer(server) {
    if (!tlsDir) return
    server.middlewares.use('/floodpulse-local-ca.crt', (req, res) => {
      res.setHeader('Content-Type', 'application/x-x509-ca-cert')
      res.setHeader('Content-Disposition', 'attachment; filename="floodpulse-local-ca.crt"')
      res.end(fs.readFileSync(path.join(tlsDir, 'ca.crt')))
    })
  },
}
// xfwd: the backend (uvicorn trusts forwarding only from 127.0.0.1) sees each device's own address, so
// rate limits and login lockouts are per device instead of shared by everything behind this proxy.
const proxy = { '/api': { target: apiTarget, xfwd: true } }

export default defineConfig({
  plugins: [localCertificate],
  server: { proxy, headers: securityHeaders, ...(https ? { https } : {}), ...(allowedHosts.length ? { allowedHosts } : {}) },
  preview: { proxy, headers: securityHeaders },
})
