import apiClient from './client'

export interface ContainerInfo {
  id: string
  full_id: string
  name: string
  image: string
  status: string
  state: string
  category: 'data' | 'backend' | 'workers' | 'frontend' | 'init' | 'other'
}

export interface LogLine {
  text: string
  stream: 'stdout' | 'stderr'
}

export interface ContainerLogs {
  container_id: string
  lines: LogLine[]
  total: number
}

export interface AuditLogEntry {
  id: number
  action: string
  resource_type: string | null
  resource_id: string | null
  details: Record<string, unknown>
  user_email: string
  created_at: string
}

export interface AuditLogsResponse {
  total: number
  page: number
  per_page: number
  entries: AuditLogEntry[]
}

export const listContainers = () => apiClient.get<ContainerInfo[]>('/api/v1/logs/containers')
export const getContainerLogs = (id: string, tail = 300) =>
  apiClient.get<ContainerLogs>(`/api/v1/logs/containers/${id}`, { params: { tail } })
export const getAuditLogs = (page = 1, perPage = 50, action?: string, resourceType?: string) =>
  apiClient.get<AuditLogsResponse>('/api/v1/logs/audit', {
    params: { page, per_page: perPage, ...(action ? { action } : {}), ...(resourceType ? { resource_type: resourceType } : {}) },
  })
