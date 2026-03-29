import apiClient from './client'

export interface NetworkNode {
  id: string
  ip_address: string
  mac_address: string | null
  hostname: string | null
  os_family: string | null
  os_version: string | null
  device_type: 'pc' | 'mobile' | 'router' | 'switch' | 'server' | 'printer' | 'iot' | 'unknown'
  open_ports: number[]
  services: Array<{ port: number; protocol: string; service: string; product: string; version: string }>
  status: 'active' | 'inactive'
  network_range: string | null
  first_discovered_at: string | null
  last_seen_at: string | null
}

export interface NetworkScan {
  id: string
  scan_type: string
  target: string | null
  network_range: string | null
  status: 'pending' | 'running' | 'completed' | 'failed'
  nodes_found: number
  result: Record<string, unknown>
  error: string | null
  started_at: string | null
  completed_at: string | null
}

export interface NetworkStatus {
  hostname: string
  host_ip: string
  interfaces: Array<{ interface: string; ip: string; prefix: number; network_range: string; family: string }>
  primary_range: string | null
}

export const getNetworkStatus = () => apiClient.get<NetworkStatus>('/api/v1/network/status')
export const discoverNetwork = (network_range?: string) =>
  apiClient.post<{ scan_id: string; status: string; message: string }>('/api/v1/network/discover', { network_range })
export const getNodes = () => apiClient.get<NetworkNode[]>('/api/v1/network/nodes')
export const getNode = (id: string) => apiClient.get<NetworkNode>(`/api/v1/network/nodes/${id}`)
export const scanNode = (id: string, profile: string) =>
  apiClient.post<{ scan_id: string; status: string; message: string }>(`/api/v1/network/nodes/${id}/scan`, { profile })
export const deleteNode = (id: string) => apiClient.delete(`/api/v1/network/nodes/${id}`)
export const getScan = (id: string) => apiClient.get<NetworkScan>(`/api/v1/network/scans/${id}`)
export const listScans = () => apiClient.get<NetworkScan[]>('/api/v1/network/scans')
