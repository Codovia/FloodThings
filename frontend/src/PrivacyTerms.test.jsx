import React from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import PrivacyTerms from './PrivacyTerms.jsx'

afterEach(cleanup)
it('states what is stored and the prototype terms, with emergency numbers', () => {
  render(<PrivacyTerms navigate={vi.fn()} />)
  const text = () => document.body.textContent
  expect(text()).toContain('Photos are deleted after 7 days and the private details after 30 days')
  expect(text()).toContain('/stop deletes it'); expect(text()).toContain('not the coordinates in web addresses')
  fireEvent.click(screen.getByRole('tab', { name: 'Terms of use' }))
  expect(text()).toContain('Not an official warning service.')
  expect(screen.getByRole('link', { name: '112' }).getAttribute('href')).toBe('tel:112')
  expect(screen.getByRole('link', { name: 'Model performance' }).getAttribute('href')).toBe('/model-performance')
})
