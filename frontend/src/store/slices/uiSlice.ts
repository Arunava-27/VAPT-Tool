import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

interface UiState {
  sidebarOpen: boolean
  theme: 'dark' | 'light'
}

const initialState: UiState = {
  sidebarOpen: true,
  theme: 'dark',
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar(state) {
      state.sidebarOpen = !state.sidebarOpen
    },
    setSidebarOpen(state, action: PayloadAction<boolean>) {
      state.sidebarOpen = action.payload
    },
    toggleTheme(state) {
      state.theme = state.theme === 'dark' ? 'light' : 'dark'
    },
  },
})

export const { toggleSidebar, setSidebarOpen, toggleTheme } = uiSlice.actions
export default uiSlice.reducer
