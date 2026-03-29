import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from '../components/layout/AppLayout'
import ProtectedRoute from './ProtectedRoute'
import LoginPage from '../pages/auth/LoginPage'
import SetupPage from '../pages/auth/SetupPage'
import DashboardPage from '../pages/dashboard/DashboardPage'
import ScansPage from '../pages/scans/ScansPage'
import NewScanPage from '../pages/scans/NewScanPage'
import ScanDetailPage from '../pages/scans/ScanDetailPage'
import SettingsPage from '../pages/settings/SettingsPage'
import InfraPage from '../pages/infra/InfraPage'
import UsersPage from '../pages/admin/UsersPage'
import NetworkPage from '../pages/network/NetworkPage'
import LogsPage from '../pages/logs/LogsPage'

interface AppRouterProps {
  setupRequired?: boolean
}

export default function AppRouter({ setupRequired }: AppRouterProps) {
  return (
    <Routes>
      {/* First-run setup — public */}
      <Route path="/setup" element={<SetupPage />} />

      {/* If setup required, send everything to /setup */}
      {setupRequired && (
        <Route path="*" element={<Navigate to="/setup" replace />} />
      )}

      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/network" element={<NetworkPage />} />
        <Route path="/scans" element={<ScansPage />} />
        <Route path="/scans/new" element={<NewScanPage />} />
        <Route path="/scans/:id" element={<ScanDetailPage />} />
        <Route path="/infra" element={<InfraPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/admin/users" element={<UsersPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
