import { Navigate } from 'react-router-dom'
import { useSelector } from 'react-redux'
import type { RootState } from '../store'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useSelector((s: RootState) => s.auth.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}
