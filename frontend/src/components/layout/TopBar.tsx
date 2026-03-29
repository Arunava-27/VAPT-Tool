import { Menu, Bell } from 'lucide-react'
import { useDispatch } from 'react-redux'
import { toggleSidebar } from '../../store/slices/uiSlice'

interface Props { title: string }

export default function TopBar({ title }: Props) {
  const dispatch = useDispatch()
  return (
    <header className="h-14 bg-cyber-surface border-b border-cyber-border flex items-center px-4 gap-4">
      <button
        onClick={() => dispatch(toggleSidebar())}
        aria-label="Toggle sidebar"
        className="text-slate-400 hover:text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyber-primary/50 rounded"
      >
        <Menu className="w-5 h-5" />
      </button>
      <h1 className="text-sm font-semibold text-white flex-1">{title}</h1>
      <button aria-label="Notifications" className="text-slate-400 hover:text-white transition-colors relative">
        <Bell className="w-5 h-5" />
      </button>
    </header>
  )
}
