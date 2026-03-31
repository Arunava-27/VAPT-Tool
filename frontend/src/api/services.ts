// Direct client to host-agent (localhost:9999)
// Bypasses api-gateway so service control works even when gateway is down

const HOST_AGENT = 'http://localhost:9999'

export type ServiceStatus = 'running' | 'stopped' | 'unknown' | 'starting' | 'stopping'
export type ServiceType = 'docker' | 'native' | 'worker'
export type ServiceCategory = 'data' | 'backend' | 'worker'

export interface ServiceInfo {
  id: string
  label: string
  category: ServiceCategory
  type: ServiceType
  icon: string
  status: ServiceStatus
  // native/worker only
  pid?: number | null
  cpu_percent?: number
  memory_mb?: number
  uptime_seconds?: number
  port?: number
  self?: boolean
  // docker only
  container?: string
  state?: string
  started_at?: string
}

async function agentFetch(path: string, options?: RequestInit): Promise<Response> {
  return fetch(`${HOST_AGENT}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  })
}

export async function listAllServices(): Promise<ServiceInfo[]> {
  const r = await agentFetch('/services')
  if (!r.ok) throw new Error(`Failed to list services: ${r.status}`)
  return r.json()
}

export async function startService(name: string): Promise<{ ok: boolean; message: string; pid?: number }> {
  const r = await agentFetch(`/services/${name}/start`, { method: 'POST' })
  return r.json()
}

export async function stopService(name: string): Promise<{ ok: boolean; message: string }> {
  const r = await agentFetch(`/services/${name}/stop`, { method: 'POST' })
  return r.json()
}

export async function getServiceLogs(
  name: string,
  lines = 150,
): Promise<{ lines: Array<{ text: string; stream: string }> }> {
  const r = await agentFetch(`/services/${name}/logs?lines=${lines}`)
  if (!r.ok) return { lines: [] }
  return r.json()
}
