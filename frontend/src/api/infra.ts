import apiClient from './client'

export interface ServiceHealth {
  id: string
  name: string
  description?: string
  category: 'database' | 'cache' | 'queue' | 'search' | 'storage' | 'backend' | 'worker' | 'secrets'
  status: 'healthy' | 'unhealthy' | 'unreachable' | 'degraded' | 'running' | 'stopped' | 'not_started'
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
  // Native worker extras
  host?: 'host_machine' | 'docker'
  pid?: number
  uptime?: string
  cpu_percent?: number
  memory_mb?: number
  threads?: number
  label?: string
}

export interface NativeWorkerStatus {
  name: string
  label: string
  queue: string
  description: string
  status: 'running' | 'stopped' | 'not_started'
  pid: number | null
  alive: boolean
  stats: {
    cpu_percent?: number
    memory_mb?: number
    threads?: number
    status?: string
    create_time?: number
  }
  log_file: string
  err_file: string
  last_log_lines: string[]
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

export interface HostAgentStatus {
  status: 'online' | 'offline'
  pid?: number | null
  uptime_s?: number
  memory_mb?: number
  cpu_percent?: number
  version?: string
  port?: number
  error?: string
}

export const getServicesHealth = () =>
  apiClient.get<ServicesHealthResponse>('/api/v1/health/services')

export const getHostAgentStatus = () =>
  apiClient.get<HostAgentStatus>('/api/v1/health/host-agent')

export const shutdownHostAgent = () =>
  apiClient.post<{ ok: boolean; message: string }>('/api/v1/health/host-agent/shutdown')

export const getNativeWorkers = () =>
  apiClient.get<NativeWorkerStatus[]>('/api/v1/health/workers')

export const getNativeWorkerLogs = (name: string, tail = 200, stream: 'stdout' | 'stderr' | 'all' = 'stderr') =>
  apiClient.get<{ worker: string; lines: { stream: string; text: string }[]; total: number }>(
    `/api/v1/health/workers/${name}/logs`,
    { params: { tail, stream } }
  )

export const getServiceDetail = (serviceId: string) =>
  apiClient.get<ServiceDetail>(`/api/v1/health/services/${serviceId}/detail`)

export const runServiceAction = (serviceId: string, action: string, params?: Record<string, unknown>) =>
  apiClient.post<{ ok: boolean; message: string }>(
    `/api/v1/health/services/${serviceId}/action`,
    { action, params }
  )
