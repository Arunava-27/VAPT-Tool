import clsx from 'clsx'
import type { ScanStatus } from '../../types'
import { statusDot } from '../../utils/severity'

export default function StatusDot({ status }: { status: ScanStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={clsx('w-2 h-2 rounded-full', statusDot[status])} />
    </span>
  )
}
