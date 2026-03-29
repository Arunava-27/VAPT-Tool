import { useState } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { User, Moon, Sun, Save, KeyRound, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import type { RootState } from '../../store'
import { toggleTheme } from '../../store/slices/uiSlice'
import { setUser } from '../../store/slices/authSlice'
import { updateProfile, changePassword } from '../../api/users'

type Status = { type: 'success' | 'error'; msg: string } | null

function StatusBanner({ status }: { status: Status }) {
  if (!status) return null
  const isErr = status.type === 'error'
  return (
    <div className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm ${isErr ? 'bg-red-500/10 border border-red-500/30 text-red-400' : 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400'}`}>
      {isErr ? <AlertCircle className="w-4 h-4 shrink-0" /> : <CheckCircle className="w-4 h-4 shrink-0" />}
      {status.msg}
    </div>
  )
}

function InputField({ label, type = 'text', value, onChange, placeholder }: {
  label: string; type?: string; value: string; onChange: (v: string) => void; placeholder?: string
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs text-slate-500">{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary transition-colors"
      />
    </div>
  )
}

export default function SettingsPage() {
  const user = useSelector((s: RootState) => s.auth.user)
  const theme = useSelector((s: RootState) => s.ui.theme)
  const dispatch = useDispatch()

  // Profile form
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [profileStatus, setProfileStatus] = useState<Status>(null)
  const [profileLoading, setProfileLoading] = useState(false)

  // Password form
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirmPwd, setConfirmPwd] = useState('')
  const [pwdStatus, setPwdStatus] = useState<Status>(null)
  const [pwdLoading, setPwdLoading] = useState(false)

  async function handleProfileSave() {
    setProfileStatus(null)
    const payload: Record<string, string> = {}
    if (fullName.trim() && fullName.trim() !== user?.full_name) payload.full_name = fullName.trim()
    if (email.trim() && email.trim() !== user?.email) payload.email = email.trim()
    if (!Object.keys(payload).length) {
      setProfileStatus({ type: 'error', msg: 'No changes to save.' })
      return
    }
    setProfileLoading(true)
    try {
      const updated = await updateProfile(payload)
      dispatch(setUser({ ...user, ...updated }))
      setProfileStatus({ type: 'success', msg: 'Profile updated successfully.' })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setProfileStatus({ type: 'error', msg: detail ?? 'Failed to update profile.' })
    } finally {
      setProfileLoading(false)
    }
  }

  async function handlePasswordChange() {
    setPwdStatus(null)
    if (!currentPwd || !newPwd || !confirmPwd) {
      setPwdStatus({ type: 'error', msg: 'All fields are required.' })
      return
    }
    if (newPwd.length < 8) {
      setPwdStatus({ type: 'error', msg: 'New password must be at least 8 characters.' })
      return
    }
    if (newPwd !== confirmPwd) {
      setPwdStatus({ type: 'error', msg: 'New passwords do not match.' })
      return
    }
    setPwdLoading(true)
    try {
      await changePassword({ current_password: currentPwd, new_password: newPwd, confirm_password: confirmPwd })
      setPwdStatus({ type: 'success', msg: 'Password changed successfully.' })
      setCurrentPwd(''); setNewPwd(''); setConfirmPwd('')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setPwdStatus({ type: 'error', msg: detail ?? 'Failed to change password.' })
    } finally {
      setPwdLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">Manage your account and preferences</p>
      </div>

      {/* Profile */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <User className="w-4 h-4 text-cyber-primary" />
          <h2 className="text-sm font-semibold text-slate-300">Profile</h2>
          <span className="ml-auto text-xs px-2 py-0.5 rounded border border-cyber-border text-slate-500 font-mono">
            {user?.is_superuser ? 'Super Admin' : (user?.roles?.[0] ?? 'User')}
          </span>
        </div>

        <InputField label="Full Name" value={fullName} onChange={setFullName} placeholder="Your display name" />
        <InputField label="Email Address" type="email" value={email} onChange={setEmail} placeholder="you@example.com" />

        <div className="flex items-center justify-between pt-1">
          <StatusBanner status={profileStatus} />
          <button
            onClick={handleProfileSave}
            disabled={profileLoading}
            className="ml-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-primary text-black text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {profileLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Changes
          </button>
        </div>

        {/* Read-only info */}
        <div className="pt-3 border-t border-cyber-border space-y-2">
          {[
            { label: 'Tenant ID', value: user?.tenant_id ?? '—' },
          ].map(({ label, value }) => (
            <div key={label} className="flex justify-between items-center py-1">
              <span className="text-xs text-slate-500">{label}</span>
              <span className="text-xs text-slate-400 font-mono">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Change Password */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <KeyRound className="w-4 h-4 text-cyber-primary" />
          <h2 className="text-sm font-semibold text-slate-300">Change Password</h2>
        </div>

        <InputField label="Current Password" type="password" value={currentPwd} onChange={setCurrentPwd} placeholder="••••••••" />
        <InputField label="New Password" type="password" value={newPwd} onChange={setNewPwd} placeholder="Min. 8 characters" />
        <InputField label="Confirm New Password" type="password" value={confirmPwd} onChange={setConfirmPwd} placeholder="Repeat new password" />

        <div className="flex items-center justify-between pt-1">
          <StatusBanner status={pwdStatus} />
          <button
            onClick={handlePasswordChange}
            disabled={pwdLoading}
            className="ml-auto flex items-center gap-2 px-4 py-2 rounded-lg bg-cyber-primary text-black text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {pwdLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
            Update Password
          </button>
        </div>
      </div>

      {/* Appearance */}
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

