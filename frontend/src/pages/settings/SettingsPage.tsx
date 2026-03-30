import { useState, useEffect } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { User, Moon, Sun, Save, KeyRound, CheckCircle, AlertCircle, Loader2, Cloud, Server, Trash2, ChevronDown, ChevronRight } from 'lucide-react'
import type { RootState } from '../../store'
import { toggleTheme } from '../../store/slices/uiSlice'
import { setUser } from '../../store/slices/authSlice'
import { updateProfile, changePassword } from '../../api/users'
import { getCloudCredentials, saveCloudCredential, deleteCloudCredential, testCloudCredential, type CloudCredential } from '../../api/settings'
import toast from 'react-hot-toast'

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

function CloudCredentialsCard() {
  const [credentials, setCredentials] = useState<CloudCredential[]>([])
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [testing, setTesting] = useState<Record<string, boolean>>({})
  const [deleting, setDeleting] = useState<Record<string, boolean>>({})
  const [fields, setFields] = useState<Record<string, Record<string, string>>>({
    aws: { access_key_id: '', secret_access_key: '', region: '', account_id: '' },
    gcp: { project_id: '', service_account_json: '' },
    azure: { tenant_id: '', client_id: '', client_secret: '', subscription_id: '' },
  })

  useEffect(() => {
    getCloudCredentials()
      .then(r => setCredentials(r.data))
      .catch(() => {})
  }, [])

  const getCredential = (provider: string) => credentials.find(c => c.provider === provider as CloudCredential['provider'])

  const updateField = (provider: string, key: string, value: string) => {
    setFields(prev => ({ ...prev, [provider]: { ...prev[provider], [key]: value } }))
  }

  const handleSave = async (provider: string) => {
    setSaving(prev => ({ ...prev, [provider]: true }))
    try {
      await saveCloudCredential(provider, fields[provider])
      const r = await getCloudCredentials()
      setCredentials(r.data)
      toast.success(`${provider.toUpperCase()} credentials saved`)
    } catch {
      toast.error(`Failed to save ${provider.toUpperCase()} credentials`)
    } finally {
      setSaving(prev => ({ ...prev, [provider]: false }))
    }
  }

  const handleTest = async (provider: string) => {
    setTesting(prev => ({ ...prev, [provider]: true }))
    try {
      await testCloudCredential(provider)
      toast.success(`${provider.toUpperCase()} connection successful`)
    } catch {
      toast.error(`${provider.toUpperCase()} connection failed`)
    } finally {
      setTesting(prev => ({ ...prev, [provider]: false }))
    }
  }

  const handleDelete = async (provider: string) => {
    setDeleting(prev => ({ ...prev, [provider]: true }))
    try {
      await deleteCloudCredential(provider)
      setCredentials(prev => prev.filter(c => c.provider !== provider as CloudCredential['provider']))
      toast.success(`${provider.toUpperCase()} credentials removed`)
    } catch {
      toast.error(`Failed to remove ${provider.toUpperCase()} credentials`)
    } finally {
      setDeleting(prev => ({ ...prev, [provider]: false }))
    }
  }

  const providers = [
    {
      id: 'aws', label: 'Amazon Web Services', icon: Cloud,
      fields: [
        { key: 'access_key_id', label: 'Access Key ID', type: 'text' },
        { key: 'secret_access_key', label: 'Secret Access Key', type: 'password' },
        { key: 'region', label: 'Default Region', type: 'text', placeholder: 'us-east-1' },
        { key: 'account_id', label: 'Account ID (optional)', type: 'text' },
      ],
    },
    {
      id: 'gcp', label: 'Google Cloud Platform', icon: Server,
      fields: [
        { key: 'project_id', label: 'Project ID', type: 'text' },
        { key: 'service_account_json', label: 'Service Account JSON', type: 'textarea' },
      ],
    },
    {
      id: 'azure', label: 'Microsoft Azure', icon: Cloud,
      fields: [
        { key: 'tenant_id', label: 'Tenant ID', type: 'text' },
        { key: 'client_id', label: 'Client ID', type: 'text' },
        { key: 'client_secret', label: 'Client Secret', type: 'password' },
        { key: 'subscription_id', label: 'Subscription ID', type: 'text' },
      ],
    },
  ]

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Cloud className="w-4 h-4 text-cyber-primary" />
        <h2 className="text-sm font-semibold text-slate-300">Cloud Credentials</h2>
      </div>
      <p className="text-xs text-slate-500">Configure cloud provider credentials for cloud security scanning.</p>
      <div className="space-y-3">
        {providers.map(({ id, label, icon: Icon, fields: providerFields }) => {
          const cred = getCredential(id)
          const isExpanded = expanded[id]
          return (
            <div key={id} className="border border-cyber-border rounded-lg overflow-hidden">
              <button
                onClick={() => setExpanded(prev => ({ ...prev, [id]: !prev[id] }))}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-cyber-bg transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Icon className="w-4 h-4 text-slate-400" />
                  <span className="text-sm font-medium text-slate-200">{label}</span>
                  {cred && (
                    <span className="text-xs px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">Connected</span>
                  )}
                </div>
                {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-500" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
              </button>
              {isExpanded && (
                <div className="px-4 pb-4 space-y-3 border-t border-cyber-border">
                  {cred && (
                    <div className="mt-3 p-3 bg-cyber-bg rounded-lg text-xs text-slate-500">
                      <p className="font-semibold text-slate-400 mb-1">Saved credentials (masked):</p>
                      {Object.entries(cred.config).map(([k, v]) => (
                        <div key={k} className="flex justify-between">
                          <span>{k}</span>
                          <span className="font-mono">{v}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {providerFields.map(({ key, label: fieldLabel, type, placeholder }) => (
                    <div key={key} className="space-y-1.5 mt-3">
                      <label className="text-xs text-slate-500">{fieldLabel}</label>
                      {type === 'textarea' ? (
                        <textarea
                          value={fields[id][key] ?? ''}
                          onChange={e => updateField(id, key, e.target.value)}
                          rows={4}
                          placeholder={placeholder ?? fieldLabel}
                          className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary transition-colors font-mono"
                        />
                      ) : (
                        <input
                          type={type}
                          value={fields[id][key] ?? ''}
                          onChange={e => updateField(id, key, e.target.value)}
                          placeholder={placeholder ?? fieldLabel}
                          className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary transition-colors"
                        />
                      )}
                    </div>
                  ))}
                  <div className="flex gap-2 pt-2">
                    <button
                      onClick={() => handleSave(id)}
                      disabled={saving[id]}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-cyber-primary text-black text-xs font-semibold hover:opacity-90 disabled:opacity-50 transition-opacity"
                    >
                      {saving[id] ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                      Save
                    </button>
                    {cred && (
                      <>
                        <button
                          onClick={() => handleTest(id)}
                          disabled={testing[id]}
                          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-cyber-border text-xs text-slate-400 hover:text-white hover:border-cyber-primary disabled:opacity-50 transition-colors"
                        >
                          {testing[id] ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                          Test Connection
                        </button>
                        <button
                          onClick={() => handleDelete(id)}
                          disabled={deleting[id]}
                          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-rose-500/30 text-xs text-rose-400 hover:bg-rose-500/10 disabled:opacity-50 transition-colors ml-auto"
                        >
                          {deleting[id] ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                          Disconnect
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
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

      {/* Cloud Credentials */}
      <CloudCredentialsCard />

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

