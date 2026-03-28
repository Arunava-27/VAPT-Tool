import { useEffect, useState } from 'react'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { store } from './store'
import { setUser, logout } from './store/slices/authSlice'
import { getMe } from './api/auth'
import AppRouter from './router'
import LoadingSpinner from './components/common/LoadingSpinner'

// Rehydrates user state on page refresh if a token exists in localStorage
function AuthLoader({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      setReady(true)
      return
    }
    getMe()
      .then((res) => store.dispatch(setUser(res.data)))
      .catch(() => store.dispatch(logout()))
      .finally(() => setReady(true))
  }, [])

  if (!ready) {
    return (
      <div className="min-h-screen bg-cyber-bg flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }
  return <>{children}</>
}

export default function App() {
  return (
    <Provider store={store}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AuthLoader>
          <AppRouter />
        </AuthLoader>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#0d1426',
            color: '#e2e8f0',
            border: '1px solid #1e2d4a',
            fontSize: '14px',
          },
          success: { iconTheme: { primary: '#00d4ff', secondary: '#0d1426' } },
          error: { iconTheme: { primary: '#f43f5e', secondary: '#0d1426' } },
        }}
      />
    </Provider>
  )
}
