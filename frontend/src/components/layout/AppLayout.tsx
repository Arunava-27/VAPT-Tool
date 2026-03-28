import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'

const titles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/scans': 'Security Scans',
  '/scans/new': 'New Scan',
  '/infra': 'Infrastructure Monitor',
  '/settings': 'Settings',
}

export default function AppLayout() {
  const { pathname } = useLocation()
  const title = titles[pathname] ?? (pathname.startsWith('/scans/') ? 'Scan Detail' : 'VAPT Platform')

  return (
    <div className="flex h-screen bg-cyber-bg overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar title={title} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
