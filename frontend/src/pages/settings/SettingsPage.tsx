import { useSelector, useDispatch } from 'react-redux'
import { User, Moon, Sun } from 'lucide-react'
import type { RootState } from '../../store'
import { toggleTheme } from '../../store/slices/uiSlice'

export default function SettingsPage() {
  const user = useSelector((s: RootState) => s.auth.user)
  const theme = useSelector((s: RootState) => s.ui.theme)
  const dispatch = useDispatch()

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">Manage your account and preferences</p>
      </div>

      {/* Profile */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 space-y-4">
        <div className="flex items-center gap-3 mb-4">
          <User className="w-4 h-4 text-cyber-primary" />
          <h2 className="text-sm font-semibold text-slate-300">Profile</h2>
        </div>
        {[
          { label: 'Full Name', value: user?.full_name ?? '—' },
          { label: 'Email', value: user?.email ?? '—' },
          { label: 'Role', value: user?.is_superuser ? 'Super Administrator' : (user?.roles?.[0] ?? 'User') },
          { label: 'Tenant ID', value: user?.tenant_id ?? '—' },
        ].map(({ label, value }) => (
          <div key={label} className="flex justify-between items-center py-3 border-b border-cyber-border last:border-0">
            <span className="text-xs text-slate-500">{label}</span>
            <span className="text-sm text-white font-mono">{value}</span>
          </div>
        ))}
      </div>

      {/* Theme */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-300">Appearance</p>
            <p className="text-xs text-slate-500 mt-0.5">Currently: {theme} mode</p>
          </div>
          <button onClick={() => dispatch(toggleTheme())}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-cyber-border text-sm text-slate-400 hover:text-white hover:border-cyber-primary transition-colors">
            {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            {theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
          </button>
        </div>
      </div>

      {/* Permissions */}
      {user?.permissions && user.permissions.length > 0 && (
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Permissions</h2>
          <div className="flex flex-wrap gap-2">
            {user.permissions.map((p) => (
              <span key={p} className="px-2 py-1 text-xs rounded border border-cyber-border text-slate-400 font-mono">{p}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
