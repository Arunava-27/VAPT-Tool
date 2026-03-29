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

export const listContainers = () => apiClient.get<ContainerInfo[]>('/api/v1/logs/containers')
export const getContainerLogs = (id: string, tail = 300) =>
  apiClient.get<ContainerLogs>(`/api/v1/logs/containers/${id}`, { params: { tail } })
