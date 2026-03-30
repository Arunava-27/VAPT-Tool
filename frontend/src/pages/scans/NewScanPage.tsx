import { useState } from 'react'
import { useFieldArray, useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { Plus, Trash2, ArrowLeft, Calendar } from 'lucide-react'
import toast from 'react-hot-toast'
import { createScan } from '../../api/scans'
import { addScan } from '../../store/slices/scansSlice'
import LoadingSpinner from '../../components/common/LoadingSpinner'

const schema = z.object({
  name: z.string().min(3, 'Name must be at least 3 characters'),
  description: z.string().optional(),
  scan_type: z.enum(['network', 'web', 'cloud', 'container', 'full']),
  targets: z.array(z.object({
    type: z.enum(['ip', 'domain', 'cidr', 'url', 'hostname']),
    value: z.string().min(1, 'Target value is required'),
  })).min(1, 'At least one target is required'),
})
type FormData = z.infer<typeof schema>

const inputCls = 'w-full bg-cyber-bg border border-cyber-border rounded-lg px-3.5 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary focus:ring-1 focus:ring-cyber-primary/30 transition-colors'
const labelCls = 'block text-xs font-medium text-slate-400 mb-1.5'

export default function NewScanPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { register, control, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { scan_type: 'network', targets: [{ type: 'hostname', value: '' }] },
  })
  const { fields, append, remove } = useFieldArray({ control, name: 'targets' })
  const scanType = useWatch({ control, name: 'scan_type' })

  // ZAP web scan extra options (not in zod schema - added to scan_config manually)
  const [zapAuth, setZapAuth] = useState<'none' | 'form' | 'header'>('none')
  const [zapLoginUrl, setZapLoginUrl] = useState('')
  const [zapUsername, setZapUsername] = useState('')
  const [zapPassword, setZapPassword] = useState('')
  const [zapHeaderName, setZapHeaderName] = useState('Authorization')
  const [zapHeaderValue, setZapHeaderValue] = useState('')
  const [zapScanMode, setZapScanMode] = useState<'passive' | 'active'>('active')

  // Scheduling
  const [scheduleMode, setScheduleMode] = useState<'now' | 'later'>('now')
  const [scheduledAt, setScheduledAt] = useState('')

  const onSubmit = async (data: FormData) => {
    try {
      const scan_config: Record<string, unknown> = {}

      if (data.scan_type === 'web') {
        scan_config.zap_auth = zapAuth
        scan_config.zap_scan_mode = zapScanMode
        if (zapAuth === 'form') {
          scan_config.zap_login_url = zapLoginUrl
          scan_config.zap_username = zapUsername
          scan_config.zap_password = zapPassword
        } else if (zapAuth === 'header') {
          scan_config.zap_header_name = zapHeaderName
          scan_config.zap_header_value = zapHeaderValue
        }
      }

      if (scheduleMode === 'later' && scheduledAt) {
        scan_config.scheduled_at = scheduledAt
      }

      const res = await createScan({
        name: data.name,
        description: data.description,
        scan_type: data.scan_type,
        targets: data.targets,
        scan_config: Object.keys(scan_config).length ? scan_config : undefined,
      })
      dispatch(addScan(res.data))
      toast.success(scheduleMode === 'later' ? 'Scan scheduled!' : 'Scan started!')
      navigate(`/scans/${res.data.id}`)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(typeof msg === 'string' ? msg : 'Failed to create scan')
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="text-slate-400 hover:text-white transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">New Security Scan</h1>
          <p className="text-sm text-slate-500">Configure and launch a vulnerability scan</p>
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="bg-cyber-surface border border-cyber-border rounded-xl p-6 space-y-6">
        {/* Scan Name */}
        <div>
          <label className={labelCls}>Scan Name *</label>
          <input {...register('name')} className={inputCls} placeholder="e.g. Production Server Scan" />
          {errors.name && <p className="mt-1 text-xs text-rose-400">{errors.name.message}</p>}
        </div>

        {/* Description */}
        <div>
          <label className={labelCls}>Description</label>
          <textarea {...register('description')} rows={2} className={inputCls} placeholder="Optional description…" />
        </div>

        {/* Scan Type */}
        <div>
          <label className={labelCls}>Scan Type *</label>
          <select {...register('scan_type')} className={inputCls}>
            <option value="network">Network Scan (Nmap)</option>
            <option value="web">Web Application (ZAP)</option>
            <option value="cloud">Cloud Security (Prowler)</option>
            <option value="container">Container / Image (Trivy)</option>
            <option value="full">Full Scan (All Tools)</option>
          </select>
        </div>

        {/* ZAP Web Scan Options */}
        {scanType === 'web' && (
          <div className="border border-cyber-border rounded-lg p-4 space-y-4 bg-cyber-bg/50">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">ZAP Web Scan Options</p>

            {/* Scan Mode */}
            <div>
              <label className={labelCls}>Scan Mode</label>
              <div className="flex gap-3">
                {([['active', 'Active + Passive (recommended)'], ['passive', 'Passive Only']] as const).map(([val, lbl]) => (
                  <label key={val} className="flex items-center gap-2 cursor-pointer">
                    <input type="radio" value={val} checked={zapScanMode === val} onChange={() => setZapScanMode(val)} className="accent-cyber-primary" />
                    <span className="text-sm text-slate-300">{lbl}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Authentication */}
            <div>
              <label className={labelCls}>Authentication</label>
              <select value={zapAuth} onChange={e => setZapAuth(e.target.value as typeof zapAuth)} className={inputCls}>
                <option value="none">None</option>
                <option value="form">Form-based</option>
                <option value="header">Header-based</option>
              </select>
            </div>

            {zapAuth === 'form' && (
              <div className="space-y-3 pl-3 border-l border-cyber-border">
                <div>
                  <label className={labelCls}>Login URL</label>
                  <input type="url" value={zapLoginUrl} onChange={e => setZapLoginUrl(e.target.value)} className={inputCls} placeholder="https://example.com/login" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Username</label>
                    <input type="text" value={zapUsername} onChange={e => setZapUsername(e.target.value)} className={inputCls} placeholder="admin" />
                  </div>
                  <div>
                    <label className={labelCls}>Password</label>
                    <input type="password" value={zapPassword} onChange={e => setZapPassword(e.target.value)} className={inputCls} placeholder="••••••••" />
                  </div>
                </div>
              </div>
            )}

            {zapAuth === 'header' && (
              <div className="space-y-3 pl-3 border-l border-cyber-border">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Header Name</label>
                    <input type="text" value={zapHeaderName} onChange={e => setZapHeaderName(e.target.value)} className={inputCls} placeholder="Authorization" />
                  </div>
                  <div>
                    <label className={labelCls}>Header Value</label>
                    <input type="text" value={zapHeaderValue} onChange={e => setZapHeaderValue(e.target.value)} className={inputCls} placeholder="Bearer token123" />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Targets */}
        <div>
          <label className={labelCls}>Targets *</label>
          <div className="space-y-2">
            {fields.map((field, idx) => (
              <div key={field.id} className="flex gap-2">
                <select {...register(`targets.${idx}.type`)}
                  className="bg-cyber-bg border border-cyber-border rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-cyber-primary w-32 flex-shrink-0">
                  <option value="hostname">Hostname</option>
                  <option value="ip">IP Address</option>
                  <option value="cidr">CIDR</option>
                  <option value="domain">Domain</option>
                  <option value="url">URL</option>
                </select>
                <input {...register(`targets.${idx}.value`)}
                  className={`${inputCls} flex-1`} placeholder="scanme.nmap.org" />
                {fields.length > 1 && (
                  <button type="button" onClick={() => remove(idx)}
                    className="text-slate-500 hover:text-rose-400 transition-colors px-2">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
            {errors.targets && <p className="text-xs text-rose-400">{errors.targets.message}</p>}
          </div>
          <button type="button" onClick={() => append({ type: 'hostname', value: '' })}
            className="mt-2 flex items-center gap-1.5 text-xs text-cyber-primary hover:text-cyan-300 transition-colors">
            <Plus className="w-3.5 h-3.5" /> Add Target
          </button>
        </div>

        {/* Schedule */}
        <div className="border border-cyber-border rounded-lg p-4 space-y-3 bg-cyber-bg/50">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-slate-400" />
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Schedule</p>
          </div>
          <div className="flex gap-4">
            {([['now', 'Run now'], ['later', 'Schedule for later']] as const).map(([val, lbl]) => (
              <label key={val} className="flex items-center gap-2 cursor-pointer">
                <input type="radio" value={val} checked={scheduleMode === val} onChange={() => setScheduleMode(val)} className="accent-cyber-primary" />
                <span className="text-sm text-slate-300">{lbl}</span>
              </label>
            ))}
          </div>
          {scheduleMode === 'later' && (
            <div>
              <label className={labelCls}>Scheduled Date & Time</label>
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={e => setScheduledAt(e.target.value)}
                className={inputCls}
                min={new Date().toISOString().slice(0, 16)}
              />
            </div>
          )}
        </div>

        {/* Submit */}
        <div className="flex gap-3 pt-2">
          <button type="button" onClick={() => navigate(-1)}
            className="flex-1 py-2.5 rounded-lg border border-cyber-border text-sm text-slate-400 hover:text-white hover:border-slate-500 transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={isSubmitting}
            className="flex-1 flex items-center justify-center gap-2 bg-cyber-primary text-cyber-bg font-semibold py-2.5 rounded-lg hover:bg-cyan-300 disabled:opacity-60 transition-colors text-sm">
            {isSubmitting && <LoadingSpinner size="sm" />}
            {isSubmitting ? 'Starting…' : scheduleMode === 'later' ? '📅 Schedule Scan' : '🚀 Start Scan'}
          </button>
        </div>
      </form>
    </div>
  )
}
