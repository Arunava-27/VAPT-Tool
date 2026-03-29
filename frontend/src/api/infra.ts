import apiClient from './client'

export interface ServiceHealth {
  id: string
  name: string
  description?: string
  category: 'database' | 'cache' | 'queue' | 'search' | 'storage' | 'backend' | 'worker' | 'secrets'
  status: 'healthy' | 'unhealthy' | 'unreachable' | 'degraded'
  latency_ms?: number
  error?: string
  used_memory?: string
  cluster_status?: string
  nodes?: number | string
  concurrency?: number | string
  tasks_processed?: Record<string, number>
  // AI Engine specific
  active_model?: string
  active_provider?: string
}

export interface ServicesHealthResponse {
  overall: 'healthy' | 'degraded' | 'unhealthy'
  healthy: number
  total: number
  duration_ms: number
  services: ServiceHealth[]
}

export interface ServiceAction {
  id: string
  label: string
  variant: 'default' | 'info' | 'danger' | 'warning'
  confirm?: boolean
  confirm_message?: string
}

export interface ServiceDetail {
  actions: ServiceAction[]
  error?: string
  // AI Engine specific
  active_provider?: string
  active_model?: string
  available_providers?: string[]
  available_models?: string[]
  fallback_chain?: string
  ollama_url?: string
  guardrails_enabled?: boolean
  agent_timeout?: string
  max_tokens?: number
  [key: string]: unknown
}

export const getServicesHealth = () =>
  apiClient.get<ServicesHealthResponse>('/api/v1/health/services')

export const getServiceDetail = (serviceId: string) =>
  apiClient.get<ServiceDetail>(`/api/v1/health/services/${serviceId}/detail`)

export const runServiceAction = (serviceId: string, action: string, params?: Record<string, unknown>) =>
  apiClient.post<{ ok: boolean; message: string }>(
    `/api/v1/health/services/${serviceId}/action`,
    { action, params }
  )
