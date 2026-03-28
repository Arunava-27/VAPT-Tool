import apiClient from './client'

export interface ServiceHealth {
  id: string
  name: string
  category: 'database' | 'cache' | 'queue' | 'search' | 'storage' | 'backend' | 'worker'
  status: 'healthy' | 'unhealthy' | 'unreachable' | 'degraded'
  latency_ms?: number
  error?: string
  // extra metadata per service type
  used_memory?: string
  cluster_status?: string
  nodes?: number | string
  concurrency?: number | string
  tasks_processed?: Record<string, number>
}

export interface ServicesHealthResponse {
  overall: 'healthy' | 'degraded' | 'unhealthy'
  healthy: number
  total: number
  duration_ms: number
  services: ServiceHealth[]
}

export const getServicesHealth = () =>
  apiClient.get<ServicesHealthResponse>('/api/v1/health/services')
