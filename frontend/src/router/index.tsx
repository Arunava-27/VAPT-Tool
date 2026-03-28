import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import ProtectedRoute from './ProtectedRoute'
import LoginPage from '../pages/auth/LoginPage'
import DashboardPage from '../pages/dashboard/DashboardPage'
import ScansPage from '../pages/scans/ScansPage'
import NewScanPage from '../pages/scans/NewScanPage'
import ScanDetailPage from '../pages/scans/ScanDetailPage'
import SettingsPage from '../pages/settings/SettingsPage'

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/scans" element={<ScansPage />} />
        <Route path="/scans/new" element={<NewScanPage />} />
        <Route path="/scans/:id" element={<ScanDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
