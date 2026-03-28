import axios from 'axios'
import { store } from '../store'
import { logout, setCredentials } from '../store/slices/authSlice'

// Empty string → use relative URLs (nginx proxies /api/ and /api/v1/ws/)
// Non-empty → direct to the specified host (local dev)
const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT to every request
apiClient.interceptors.request.use((config) => {
  const token = store.getState().auth.accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let isRefreshing = false
let failedQueue: Array<{ resolve: (v: string) => void; reject: (e: unknown) => void }> = []

const processQueue = (error: unknown, token: string | null) => {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)))
  failedQueue = []
}

// Auto-refresh on 401
apiClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`
          return apiClient(original)
        })
      }
      original._retry = true
      isRefreshing = true
      const refreshToken = store.getState().auth.refreshToken
      if (!refreshToken) {
        store.dispatch(logout())
        return Promise.reject(error)
      }
      try {
        const res = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        })
        const newToken: string = res.data.access_token
        store.dispatch(setCredentials({ accessToken: newToken, refreshToken }))
        processQueue(null, newToken)
        original.headers.Authorization = `Bearer ${newToken}`
        return apiClient(original)
      } catch (err) {
        processQueue(err, null)
        store.dispatch(logout())
        window.location.href = '/login'
        return Promise.reject(err)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(error)
  },
)

export default apiClient
