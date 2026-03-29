import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shield, Loader2, AlertCircle, CheckCircle, Eye, EyeOff } from 'lucide-react'
import { initSetup } from '../../api/setup'
import toast from 'react-hot-toast'

function Field({
  label, type = 'text', value, onChange, placeholder, show, onToggle,
}: {
  label: string
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  show?: boolean
  onToggle?: () => void
}) {
  const isPassword = type === 'password'
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-slate-400">{label}</label>
      <div className="relative">
        <input
          type={isPassword ? (show ? 'text' : 'password') : type}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-[#0d1426] border border-[#1e2d4a] rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition-colors pr-10"
        />
        {isPassword && onToggle && (
          <button type="button" onClick={onToggle}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors">
            {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>
    </div>
  )
}

export default function SetupPage() {
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!fullName.trim()) return setError('Full name is required.')
    if (!email.trim()) return setError('Email is required.')
    if (password.length < 8) return setError('Password must be at least 8 characters.')
    if (password !== confirmPassword) return setError('Passwords do not match.')

    setLoading(true)
    try {
      await initSetup({ full_name: fullName.trim(), email: email.trim(), password, confirm_password: confirmPassword })
      setDone(true)
      toast.success('Super admin created! Redirecting to login…')
      setTimeout(() => navigate('/login', { replace: true }), 2000)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Setup failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#060d1a] flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 mb-4">
            <Shield className="w-7 h-7 text-cyan-400" />
          </div>
          <h1 className="text-2xl font-bold text-white">Welcome to VAPT Platform</h1>
          <p className="text-slate-400 text-sm mt-2">
            First-time setup — create your super admin account to get started.
          </p>
        </div>

        {/* Card */}
        <div className="bg-[#0d1426] border border-[#1e2d4a] rounded-2xl p-8">
          {done ? (
            <div className="text-center space-y-3">
              <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto" />
              <p className="text-white font-semibold">Setup complete!</p>
              <p className="text-slate-400 text-sm">Redirecting you to login…</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="mb-2">
                <h2 className="text-sm font-semibold text-slate-300">Create Super Admin Account</h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  This account will have full access to manage the platform, users, and settings.
                </p>
              </div>

              <Field label="Full Name" value={fullName} onChange={setFullName} placeholder="e.g. John Doe" />
              <Field label="Email Address" type="email" value={email} onChange={setEmail} placeholder="admin@yourcompany.com" />
              <Field label="Password" type="password" value={password} onChange={setPassword}
                placeholder="Min. 8 characters" show={showPwd} onToggle={() => setShowPwd(p => !p)} />
              <Field label="Confirm Password" type="password" value={confirmPassword} onChange={setConfirmPassword}
                placeholder="Repeat password" show={showConfirm} onToggle={() => setShowConfirm(p => !p)} />

              {error && (
                <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              <button type="submit" disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed mt-2">
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
                {loading ? 'Creating account…' : 'Create Super Admin'}
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-xs text-slate-600 mt-6">
          This page is only available during first-time setup.
        </p>
      </div>
    </div>
  )
}
