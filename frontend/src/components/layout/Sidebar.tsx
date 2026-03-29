import { NavLink, useNavigate } from 'react-router-dom'
import { Shield, LayoutDashboard, Search, Plus, Settings, LogOut, ChevronLeft, ChevronRight, Server, Users } from 'lucide-react'
import { useDispatch, useSelector } from 'react-redux'
import clsx from 'clsx'
import type { RootState } from '../../store'
import { toggleSidebar } from '../../store/slices/uiSlice'
import { logout } from '../../store/slices/authSlice'

const NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/scans', icon: Search, label: 'Scans' },
  { to: '/scans/new', icon: Plus, label: 'New Scan' },
  { to: '/infra', icon: Server, label: 'Infrastructure' },
]

const ADMIN_NAV = [
  { to: '/admin/users', icon: Users, label: 'Users' },
]

const BOTTOM_NAV = [
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const open = useSelector((s: RootState) => s.ui.sidebarOpen)
  const user = useSelector((s: RootState) => s.auth.user)

  const initials = user?.full_name
    ? user.full_name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.slice(0, 2).toUpperCase() ?? 'VP'

  function NavItem({ to, icon: Icon, label }: { to: string; icon: React.ElementType; label: string }) {
    return (
      <NavLink to={to}
        className={({ isActive }) => clsx(
          'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-primary/50',
          isActive
            ? 'bg-cyber-primary/10 text-cyber-primary border border-cyber-primary/20'
            : 'text-slate-400 hover:text-white hover:bg-cyber-border border border-transparent'
        )}>
        <Icon className="w-4 h-4 flex-shrink-0" />
        {open && <span>{label}</span>}
      </NavLink>
    )
  }

  return (
    <aside className={clsx('flex flex-col h-screen bg-cyber-surface border-r border-cyber-border transition-all duration-300', open ? 'w-56' : 'w-16')}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-cyber-border">
        <Shield className="w-7 h-7 text-cyber-primary flex-shrink-0" />
        {open && <span className="font-bold text-white text-sm tracking-wide">VAPT Platform</span>}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2 overflow-y-auto">
        {NAV.map(item => <NavItem key={item.to} {...item} />)}

        {/* Admin section — super admin only */}
        {user?.is_superuser && (
          <>
            {open && (
              <p className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-600">
                Administration
              </p>
            )}
            {!open && <div className="border-t border-cyber-border/50 my-2" />}
            {ADMIN_NAV.map(item => <NavItem key={item.to} {...item} />)}
          </>
        )}

        <div className="border-t border-cyber-border/50 my-2" />
        {BOTTOM_NAV.map(item => <NavItem key={item.to} {...item} />)}
      </nav>

      {/* User + collapse */}
      <div className="border-t border-cyber-border p-3 space-y-2">
        {open && (
          <div className="flex items-center gap-2 px-2 py-1">
            <div className="w-7 h-7 rounded-full bg-cyber-primary/20 border border-cyber-primary/30 flex items-center justify-center text-xs font-bold text-cyber-primary">
              {initials}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-slate-300 truncate">{user?.full_name ?? 'User'}</p>
              <p className="text-xs text-slate-500 truncate">{user?.email}</p>
            </div>
          </div>
        )}
        <button onClick={() => { dispatch(logout()); navigate('/login') }}
          className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-primary/50">
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {open && <span>Logout</span>}
        </button>
        <button onClick={() => dispatch(toggleSidebar())}
          className="flex items-center gap-3 w-full px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-cyber-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-primary/50">
          {open ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          {open && <span className="text-xs">Collapse</span>}
        </button>
      </div>
    </aside>
  )
}
