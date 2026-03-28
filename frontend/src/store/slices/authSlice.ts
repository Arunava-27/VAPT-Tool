import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { User } from '../../types'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

const initialState: AuthState = {
  user: null,
  accessToken: localStorage.getItem('access_token'),
  refreshToken: localStorage.getItem('refresh_token'),
  isAuthenticated: !!localStorage.getItem('access_token'),
  isLoading: false,
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setCredentials(state, action: PayloadAction<{ accessToken: string; refreshToken?: string | null; user?: User }>) {
      state.accessToken = action.payload.accessToken
      if (action.payload.refreshToken !== undefined) {
        state.refreshToken = action.payload.refreshToken ?? null
      }
      if (action.payload.user) state.user = action.payload.user
      state.isAuthenticated = true
      localStorage.setItem('access_token', action.payload.accessToken)
      if (action.payload.refreshToken) {
        localStorage.setItem('refresh_token', action.payload.refreshToken)
      }
    },
    setUser(state, action: PayloadAction<User>) {
      state.user = action.payload
    },
    setLoading(state, action: PayloadAction<boolean>) {
      state.isLoading = action.payload
    },
    logout(state) {
      state.user = null
      state.accessToken = null
      state.refreshToken = null
      state.isAuthenticated = false
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
    },
  },
})

export const { setCredentials, setUser, setLoading, logout } = authSlice.actions
export default authSlice.reducer
