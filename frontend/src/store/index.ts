import { configureStore } from '@reduxjs/toolkit'
import authReducer from './slices/authSlice'
import scansReducer from './slices/scansSlice'
import uiReducer from './slices/uiSlice'

export const store = configureStore({
  reducer: {
    auth: authReducer,
    scans: scansReducer,
    ui: uiReducer,
  },
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
