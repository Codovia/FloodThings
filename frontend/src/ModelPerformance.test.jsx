import React from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import ModelPerformance from './ModelPerformance.jsx'

// TEST-ONLY fixture in the /api/models/performance shape; the real numbers come from the model artifacts.
const m = (tp, fp, fn, tn, precision, recall, f1) => ({ tp, fp, fn, tn, precision, recall, f1 })
const river = (id, name, place, model, rule, served, floods) => ({ id, river: name, place, flood_level_2_year_m3s: 100, rain_rule_3d_mm: 90, train: { days: 6910, positives: 50 }, test: { days: 2192, positives: model.tp + model.fn }, model, rain_rule: rule, served, documented_floods: floods })
const FIXTURE = {
  river_flood: { version: 'river_flood_v1', target: 'TEST target', features: [], train_years: [1997, 2015], test_years: [2016, 2021],
    rivers: [river('a', 'Alpha', 'Aplace', m(24, 10, 10, 2148, .706, .706, .706), m(21, 13, 13, 2145, .618, .618, .618), true, [{ date: '2019-08-08', model_flagged: true, rule_flagged: false }]),
             river('b', 'Beta', 'Bplace', m(18, 12, 22, 2140, .6, .45, .514), m(21, 11, 19, 2141, .656, .525, .583), false, [])],
    summary: { rivers: 2, beat_rain_rule: 1, documented_floods: 1, documented_floods_flagged: 1 }, limitations: ['TEST river limitation'] },
  rainfall: { version: 'rainfall_logistic_v1', algorithm: 'TEST', target: { threshold_mm: 64.5, definition: 'TEST rain target' }, features: [],
    training: { samples: 5842, first_cutoff: '2023-01-01', last_cutoff: '2024-12-31' }, testing: { samples: 2888, first_cutoff: '2025-01-05' }, temporal_split: 'TEST',
    model: m(88, 519, 8, 2273, .145, .917, .25), baseline: m(0, 0, 96, 2792, 0, 0, 0), locations: ['Kundapur', 'Mangaluru'], limitations: ['TEST rain limitation'] },
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const open = name => fireEvent.click(screen.getByRole('tab', { name }))

it('shows the recorded results: summary, per-river table, confusion matrices and documented floods', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => FIXTURE })))
  render(<ModelPerformance navigate={vi.fn()} />)
  expect(await screen.findByText('1 of 2')).toBeTruthy()
  expect(screen.getByText(/rivers where the AI model beat a simple rain rule/)).toBeTruthy()
  expect(screen.getByText('88 of 96')).toBeTruthy(); expect(screen.getByText(/recall 92%/)).toBeTruthy()
  expect(fetch).toHaveBeenCalledWith('/api/models/performance', expect.anything())
  open('Table'); const rows = within(screen.getByRole('table')).getAllByRole('row')
  expect(rows[1].textContent).toContain('71% / 71% / 0.71'); expect(rows[2].textContent).toContain('Rain rule')
  open('Confusion matrix'); expect(screen.getByRole('group', { name: 'AI model · Alpha at Aplace' }).textContent).toContain('24hits')
  fireEvent.click(screen.getByRole('button', { name: 'Beta' })); expect(screen.getByRole('group', { name: 'AI model · Beta at Bplace' }).textContent).toContain('22missed')
  open('Real floods'); expect(screen.getByRole('table').textContent).toContain('2019-08-08')
  open('Rainfall model'); expect(screen.getByRole('group', { name: 'Baseline: always "no heavy rain"' }).textContent).toContain('96missed')
  open('River model'); expect(screen.getByRole('img', { name: /F1 score per river/ })).toBeTruthy()
})

it('an unavailable result shows no numbers in their place', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({}) })))
  render(<ModelPerformance navigate={vi.fn()} />)
  expect((await screen.findByRole('alert')).textContent).toContain('Model results are unavailable')
  expect(screen.queryByRole('tab')).toBeNull()
})
