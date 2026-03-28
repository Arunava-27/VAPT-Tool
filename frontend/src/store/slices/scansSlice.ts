import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { Scan } from '../../types'

interface ScansState {
  scans: Scan[]
  selectedScan: Scan | null
  isLoading: boolean
  error: string | null
  total: number
}

const initialState: ScansState = {
  scans: [],
  selectedScan: null,
  isLoading: false,
  error: null,
  total: 0,
}

const scansSlice = createSlice({
  name: 'scans',
  initialState,
  reducers: {
    setScans(state, action: PayloadAction<{ scans: Scan[]; total: number }>) {
      state.scans = action.payload.scans
      state.total = action.payload.total
      state.isLoading = false
      state.error = null
    },
    addScan(state, action: PayloadAction<Scan>) {
      state.scans.unshift(action.payload)
      state.total += 1
    },
    updateScan(state, action: PayloadAction<Scan>) {
      const idx = state.scans.findIndex((s) => s.id === action.payload.id)
      if (idx !== -1) state.scans[idx] = action.payload
      if (state.selectedScan?.id === action.payload.id) state.selectedScan = action.payload
    },
    /** Merge partial fields from WS / status-only updates without clobbering full scan data */
    patchScan(state, action: PayloadAction<Partial<Scan> & { id: string }>) {
      const { id, ...fields } = action.payload
      const idx = state.scans.findIndex((s) => s.id === id)
      if (idx !== -1) Object.assign(state.scans[idx], fields)
      if (state.selectedScan?.id === id) Object.assign(state.selectedScan, fields)
    },
    setSelectedScan(state, action: PayloadAction<Scan | null>) {
      state.selectedScan = action.payload
    },
    removeScan(state, action: PayloadAction<string>) {
      state.scans = state.scans.filter((s) => s.id !== action.payload)
      state.total = Math.max(0, state.total - 1)
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.isLoading = action.payload
    },
    setError(state, action: PayloadAction<string | null>) {
      state.error = action.payload
      state.isLoading = false
    },
  },
})

export const { setScans, addScan, updateScan, patchScan, setSelectedScan, removeScan, setLoading, setError } =
  scansSlice.actions
export default scansSlice.reducer
