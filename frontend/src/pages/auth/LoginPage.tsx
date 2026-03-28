import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useState } from 'react'
import { useDispatch } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { Shield, Eye, EyeOff } from 'lucide-react'
import toast from 'react-hot-toast'
import { login } from '../../api/auth'
import { getMe } from '../../api/auth'
import { setCredentials, setUser } from '../../store/slices/authSlice'
import LoadingSpinner from '../../components/common/LoadingSpinner'

const schema = z.object({
  email: z.string().email('Invalid email'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
})
type FormData = z.infer<typeof schema>

export default function LoginPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  })
  const [showPassword, setShowPassword] = useState(false)

  const onSubmit = async (data: FormData) => {
    try {
      const res = await login(data.email, data.password)
      dispatch(setCredentials({
        accessToken: res.data.access_token,
        refreshToken: res.data.refresh_token ?? null,
      }))
      const me = await getMe()
      dispatch(setUser(me.data))
      toast.success('Welcome back!')
      navigate('/dashboard')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      toast.error(typeof msg === 'string' ? msg : 'Invalid email or password')
    }
  }

  return (
    <div className="min-h-screen bg-cyber-bg flex items-center justify-center p-4">
      {/* Background grid effect */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(0,212,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(0,212,255,0.03)_1px,transparent_1px)] bg-[size:50px_50px]" />

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="bg-cyber-surface border border-cyber-border rounded-2xl p-8 shadow-2xl">
          {/* Logo */}
          <div className="flex flex-col items-center mb-8">
            <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
              <Shield className="w-7 h-7 text-cyber-primary" />
            </div>
            <h1 className="text-2xl font-bold text-white">VAPT Platform</h1>
            <p className="text-sm text-slate-500 mt-1">AI-Driven Security Testing</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Email address</label>
              <input
                {...register('email')}
                type="email"
                placeholder="admin@vapt-platform.local"
                className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3.5 py-2.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary focus:ring-1 focus:ring-cyber-primary/30 transition-colors"
              />
              {errors.email && <p className="mt-1 text-xs text-rose-400">{errors.email.message}</p>}
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Password</label>
              <div className="relative">
                <input
                  {...register('password')}
                  type={showPassword ? 'text' : 'password'}
                  placeholder="••••••••"
                  className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-3.5 py-2.5 pr-10 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyber-primary focus:ring-1 focus:ring-cyber-primary/30 transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {errors.password && <p className="mt-1 text-xs text-rose-400">{errors.password.message}</p>}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 bg-cyber-primary text-cyber-bg font-semibold py-2.5 rounded-lg hover:bg-cyan-300 disabled:opacity-60 disabled:cursor-not-allowed transition-colors text-sm"
            >
              {isSubmitting ? <LoadingSpinner size="sm" /> : null}
              {isSubmitting ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          <p className="text-center text-xs text-slate-600 mt-6">
            Private network deployment — authorised users only
          </p>
        </div>
      </div>
    </div>
  )
}
