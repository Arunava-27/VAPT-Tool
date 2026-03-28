export interface User {
  id: string
  email: string
  full_name: string
  is_superuser: boolean
  tenant_id: string
  roles: string[]
  permissions: string[]
}

export interface ScanTarget {
  type: 'ip' | 'domain' | 'cidr' | 'url' | 'hostname'
  value: string
}

export interface Scan {
  id: string
  name: string
  description?: string
  scan_type: 'network' | 'web' | 'cloud' | 'container' | 'full'
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  target: string
  scan_config: Record<string, unknown>
  result_summary?: {
    critical?: number
    high?: number
    medium?: number
    low?: number
    informational?: number
    total?: number
    ports_found?: number
  }
  error?: string
  created_at: string
  updated_at: string
  started_at?: string
  completed_at?: string
  created_by_id?: string
}

export interface CreateScanPayload {
  name: string
  description?: string
  scan_type: string
  targets: ScanTarget[]
}

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'informational'

export type ScanStatus = 'pending' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface ApiError {
  detail: string | { msg: string; type: string }[]
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
