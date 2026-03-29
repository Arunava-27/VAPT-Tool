import { useEffect, useState } from 'react'
import { Users, UserPlus, Trash2, X, Loader2, AlertCircle, Eye, EyeOff, ShieldCheck } from 'lucide-react'
import apiClient from '../../api/client'
import { listRoles } from '../../api/setup'
import toast from 'react-hot-toast'

interface UserRow {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
  role_names: string[]
  tenant_id: string
  created_at: string
}

interface Role {
  id: string
  name: string
  slug: string
  description?: string
}

const ROLE_COLORS: Record<string, string> = {
  super_admin: 'text-cyan-400 border-cyan-500/40 bg-cyan-500/10',
  tenant_admin: 'text-violet-400 border-violet-500/40 bg-violet-500/10',
  analyst: 'text-amber-400 border-amber-500/40 bg-amber-500/10',
  viewer: 'text-slate-400 border-slate-500/40 bg-slate-500/10',
}

function RoleBadge({ slug }: { slug: string }) {
  return (
    <span className={`px-2 py-0.5 text-xs rounded border font-mono ${ROLE_COLORS[slug] ?? 'text-slate-400 border-slate-500/40'}`}>
      {slug}
    </span>
  )
}

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)

  // Create form state
  const [cFullName, setCFullName] = useState('')
  const [cEmail, setCEmail] = useState('')
  const [cPassword, setCPassword] = useState('')
  const [cRoleId, setCRoleId] = useState('')
  const [cShowPwd, setCShowPwd] = useState(false)
  const [cLoading, setCLoading] = useState(false)
  const [cError, setCError] = useState<string | null>(null)

  async function loadData() {
    // Fetch users and roles independently so one failure doesn't block the other
    const [usersResult, rolesResult] = await Promise.allSettled([
      apiClient.get('/api/v1/users/'),
      listRoles(),
    ])

    if (usersResult.status === 'fulfilled') {
      setUsers(usersResult.value.data)
    } else {
      toast.error('Failed to load users.')
    }

    if (rolesResult.status === 'fulfilled') {
      const rolesData = rolesResult.value
      setRoles(rolesData)
      if (rolesData.length) setCRoleId(rolesData.find((r: { slug: string }) => r.slug === 'analyst')?.id ?? rolesData[0].id)
    } else {
      toast.error('Failed to load roles.')
    }

    setLoading(false)
  }

  useEffect(() => { loadData() }, []) // eslint-disable-line

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCError(null)
    if (!cFullName.trim()) return setCError('Full name is required.')
    if (!cEmail.trim()) return setCError('Email is required.')
    if (cPassword.length < 8) return setCError('Password must be at least 8 characters.')
    if (!cRoleId) return setCError('Please select a role.')

    // Use tenant_id from the already-loaded users list (no extra API call needed)
    const tenantId = users.length > 0 ? users[0].tenant_id : null
    if (!tenantId) return setCError('Could not determine tenant. Please try again.')

    setCLoading(true)
    try {
      await apiClient.post('/api/v1/users/', {
        email: cEmail.trim(),
        full_name: cFullName.trim(),
        password: cPassword,
        tenant_id: tenantId,
        role_ids: [cRoleId],
      })
      toast.success(`User ${cEmail} created successfully.`)
      setCFullName(''); setCEmail(''); setCPassword('')
      setShowCreate(false)
      loadData()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setCError(detail ?? 'Failed to create user.')
    } finally {
      setCLoading(false)
    }
  }

  async function handleDelete(user: UserRow) {
    if (!window.confirm(`Delete user ${user.email}? This cannot be undone.`)) return
    try {
      await apiClient.delete(`/api/v1/users/${user.id}`)
      toast.success(`User ${user.email} deleted.`)
      setUsers(prev => prev.filter(u => u.id !== user.id))
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail ?? 'Failed to delete user.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Users className="w-5 h-5 text-cyan-400" /> User Management
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage platform accounts and their roles</p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black text-sm font-semibold transition-colors">
          <UserPlus className="w-4 h-4" /> Add User
        </button>
      </div>

      {/* Users table */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 text-cyan-500 animate-spin" />
          </div>
        ) : users.length === 0 ? (
          <div className="text-center py-16 text-slate-500 text-sm">No users found.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cyber-border text-xs text-slate-500 uppercase tracking-wide">
                <th className="text-left px-5 py-3">User</th>
                <th className="text-left px-5 py-3">Role</th>
                <th className="text-left px-5 py-3">Status</th>
                <th className="text-left px-5 py-3">Joined</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} className="border-b border-cyber-border/50 last:border-0 hover:bg-white/[0.02] transition-colors">
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-cyber-primary/10 border border-cyber-primary/30 flex items-center justify-center text-xs font-bold text-cyber-primary">
                        {(u.full_name ?? u.email)[0].toUpperCase()}
                      </div>
                      <div>
                        <p className="text-white font-medium">{u.full_name ?? '—'}</p>
                        <p className="text-xs text-slate-500 font-mono">{u.email}</p>
                      </div>
                      {u.is_superuser && (
                        <span title="Super Admin">
                          <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex flex-wrap gap-1">
                      {u.role_names.length ? u.role_names.map(r => <RoleBadge key={r} slug={r} />) : <span className="text-xs text-slate-600">—</span>}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className={`px-2 py-0.5 text-xs rounded-full border ${u.is_active ? 'text-emerald-400 border-emerald-500/40 bg-emerald-500/10' : 'text-red-400 border-red-500/40 bg-red-500/10'}`}>
                      {u.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-xs text-slate-500">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    {!u.is_superuser && (
                      <button onClick={() => handleDelete(u)}
                        className="p-1.5 rounded text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-colors" title="Delete user">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Create user modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-[#0d1426] border border-[#1e2d4a] rounded-2xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <UserPlus className="w-4 h-4 text-cyan-400" /> Create New User
              </h2>
              <button onClick={() => { setShowCreate(false); setCError(null) }}
                className="p-1 rounded text-slate-500 hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs text-slate-400">Full Name</label>
                <input value={cFullName} onChange={e => setCFullName(e.target.value)} placeholder="Jane Smith"
                  className="w-full bg-[#060d1a] border border-[#1e2d4a] rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition-colors" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-slate-400">Email Address</label>
                <input type="email" value={cEmail} onChange={e => setCEmail(e.target.value)} placeholder="jane@company.com"
                  className="w-full bg-[#060d1a] border border-[#1e2d4a] rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition-colors" />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-slate-400">Temporary Password</label>
                <div className="relative">
                  <input type={cShowPwd ? 'text' : 'password'} value={cPassword} onChange={e => setCPassword(e.target.value)} placeholder="Min. 8 characters"
                    className="w-full bg-[#060d1a] border border-[#1e2d4a] rounded-lg px-3 py-2 pr-9 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 transition-colors" />
                  <button type="button" onClick={() => setCShowPwd(p => !p)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors">
                    {cShowPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-xs text-slate-400">Role</label>
                <select value={cRoleId} onChange={e => setCRoleId(e.target.value)}
                  className="w-full bg-[#060d1a] border border-[#1e2d4a] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500 transition-colors">
                  {roles.map(r => (
                    <option key={r.id} value={r.id}>{r.name}{r.description ? ` — ${r.description}` : ''}</option>
                  ))}
                </select>
              </div>

              {cError && (
                <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {cError}
                </div>
              )}

              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => { setShowCreate(false); setCError(null) }}
                  className="flex-1 py-2 rounded-lg border border-cyber-border text-sm text-slate-400 hover:text-white hover:border-slate-500 transition-colors">
                  Cancel
                </button>
                <button type="submit" disabled={cLoading}
                  className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black text-sm font-semibold transition-colors disabled:opacity-50">
                  {cLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
                  Create User
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
