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
  risk_score: number
  first_discovered_at: string | null
  last_seen_at: string | null
}

export interface NetworkScan {
  id: string
  scan_type: string
  target: string | null
  network_range: string | null
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  nodes_found: number
  result: Record<string, unknown>
  error: string | null
  started_at: string | null
  completed_at: string | null
}

export interface HostInterface {
  interface: string
  ip: string
  prefix: number
  network_range: string
  family: string
  is_docker: boolean
  is_lan: boolean
}

export interface HostInterfacesResponse {
  interfaces: HostInterface[]
  lan_interfaces: HostInterface[]
  docker_only: boolean | null
  has_lan_access: boolean
  primary_range: string | null
  gateway_ip: string | null
  error?: string
}

export interface NetworkStatus {
  hostname: string
  host_ip: string
  interfaces: Array<{ interface: string; ip: string; prefix: number; network_range: string; family: string }>
  primary_range: string | null
}

export interface HostAgentStatus {
  available: boolean
  platform: string | null
  hostname: string | null
}

export interface HostVulnerability {
  id: string
  node_id: string
  scan_id: string | null
  vuln_id: string
  title: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  description: string | null
  cve_id: string | null
  cvss_score: number | null
  port: number | null
  protocol: string | null
  service: string | null
  evidence: string | null
  remediation: string | null
  status: 'open' | 'accepted' | 'fixed' | 'false_positive'
  discovered_at: string
}

export interface TrafficConnection {
  local_ip: string
  local_port: number | null
  remote_ip: string
  remote_port: number | null
  status: string
  pid: number | null
  process_name: string | null
  family: 'IPv4' | 'IPv6'
}

export interface TrafficResponse {
  connections: TrafficConnection[]
  total: number
  error: string | null
}

export interface CapturePacket {
  type: 'packet'
  ts: number
  src: string
  dst: string
  sport: number | null
  dport: number | null
  proto: string
  length: number
  info: string
  color: string
  src_mac: string
  dst_mac: string
}

export interface CaptureInterface {
  name: string
  description: string
  ips: string[]
}

export interface TopologyNode {
  id: string
  db_id?: string
  type: 'gateway' | 'host' | 'device'
  ip: string
  hostname: string | null
  device_type: string
  risk_score: number
  open_ports: number[]
  services: Array<{ port: number; service: string }>
  status: string
  mac_address?: string | null
  os_family?: string | null
  last_seen_at?: string | null
  is_gateway: boolean
  is_host: boolean
}

export interface TopologyEdge {
  id: string
  source: string
  target: string
  type: string
}

export interface TopologyData {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  gateway_ip: string | null
  host_ip: string | null
}

export interface NetworkSummary {
  total_nodes: number
  active_nodes: number
  total_vulns: number
  critical: number
  high: number
  medium: number
  low: number
  info: number
  risk_distribution: Array<{ ip: string; risk_score: number; critical: number; high: number; medium: number }>
}

export const getNetworkStatus = () => apiClient.get<NetworkStatus>('/api/v1/network/status')
export const getHostInterfaces = () => apiClient.get<HostInterfacesResponse>('/api/v1/network/host-interfaces')
export const getHostAgentStatus = () => apiClient.get<HostAgentStatus>('/api/v1/network/host-agent-status')
export const discoverNetwork = (network_range?: string) =>
  apiClient.post<{ scan_id: string; status: string; source?: string; message: string; nodes_found?: number }>('/api/v1/network/discover', { network_range })
export const getNodes = () => apiClient.get<NetworkNode[]>('/api/v1/network/nodes')
export const getNode = (id: string) => apiClient.get<NetworkNode>(`/api/v1/network/nodes/${id}`)
export const scanNode = (id: string, profile: string) =>
  apiClient.post<{ scan_id: string; status: string; message: string }>(`/api/v1/network/nodes/${id}/scan`, { profile })
export const deleteNode = (id: string) => apiClient.delete(`/api/v1/network/nodes/${id}`)
export const getScan = (id: string) => apiClient.get<NetworkScan>(`/api/v1/network/scans/${id}`)
export const listScans = () => apiClient.get<NetworkScan[]>('/api/v1/network/scans')
export const cancelScan = (id: string) =>
  apiClient.post<{ ok: boolean; message: string }>(`/api/v1/network/scans/${id}/cancel`)
export const getNodeVulnerabilities = (nodeId: string) =>
  apiClient.get<HostVulnerability[]>(`/api/v1/network/nodes/${nodeId}/vulnerabilities`)
export const getAllVulnerabilities = (params?: { severity?: string; status?: string }) =>
  apiClient.get<HostVulnerability[]>('/api/v1/network/vulnerabilities', { params })
export const getNetworkSummary = () =>
  apiClient.get<NetworkSummary>('/api/v1/network/summary')
export const updateVulnStatus = (nodeId: string, vulnId: string, status: string) =>
  apiClient.post(`/api/v1/network/nodes/${nodeId}/vulnerabilities/${vulnId}/status`, { status })
export const getTrafficConnections = () =>
  apiClient.get<TrafficResponse>('/api/v1/network/traffic')
export const getTopology = () =>
  apiClient.get<TopologyData>('/api/v1/network/topology')
export const getCaptureInterfaces = () =>
  apiClient.get<{ interfaces: CaptureInterface[] }>('/api/v1/network/capture-interfaces')

// WebSocket URL helpers
export const getWsBase = () => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//localhost:8000`
}
export const trafficWsUrl   = (token: string, iface?: string, filter?: string) =>
  `${getWsBase()}/api/v1/ws/traffic?token=${token}${iface ? `&iface=${encodeURIComponent(iface)}` : ''}${filter ? `&filter=${encodeURIComponent(filter)}` : ''}`
export const discoveryWsUrl = (token: string, range?: string) =>
  `${getWsBase()}/api/v1/ws/discovery?token=${token}${range ? `&network_range=${encodeURIComponent(range)}` : ''}`
