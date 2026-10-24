import React from 'react'
import {afterEach,expect,it} from 'vitest'
import {cleanup,render,screen} from '@testing-library/react'
import RainfallChart from './RainfallChart.jsx'
afterEach(cleanup)
it('uses exact provider values, calendar dates and units, preserving a missing gap',()=>{render(<RainfallChart days={[{date:'2026-10-10',precipitation_mm:0},{date:'2026-10-11',precipitation_mm:12.5},{date:'2026-10-12',precipitation_mm:null}]}/>);const rows=screen.getAllByRole('listitem');expect(rows.map(r=>r.getAttribute('aria-label'))).toEqual(['2026-10-10: 0 mm forecast','2026-10-11: 12.5 mm forecast','2026-10-12: rainfall unavailable']);expect(rows[2].querySelector('.bar-track').children).toHaveLength(0);expect(rows[1].querySelector('.bar-track > div').style.height).toBe('100%');expect(screen.getByText(/neither an observation nor an AI prediction/)).toBeTruthy()})
it('empty and invalid totals never become invented chart readings',()=>{render(<RainfallChart days={[{date:'2026-10-10',precipitation_mm:-2},{date:'2026-10-11',precipitation_mm:'12'}]}/>);expect(screen.queryByRole('list')).toBeNull();expect(screen.getByText(/Rainfall visualization unavailable/)).toBeTruthy()})
