import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { store } from './store'
import AppRouter from './router'

export default function App() {
  return (
    <Provider store={store}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRouter />
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
