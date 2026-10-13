import base from './playwright.config.js'

// Verification only: existing application/isolated runner, installed real Chrome.
export default {
  ...base,
  outputDir: '/tmp/floodpulse-final-verification/playwright',
  use: { ...base.use, channel: 'chrome' },
}
