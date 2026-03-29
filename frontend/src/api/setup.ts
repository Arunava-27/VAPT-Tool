import apiClient from './client'

export interface SetupStatusResponse {
  setup_required: boolean
}

export interface SetupInitPayload {
  full_name: string
  email: string
  password: string
  confirm_password: string
}

export async function getSetupStatus(): Promise<SetupStatusResponse> {
  const res = await apiClient.get('/api/v1/setup/status')
  return res.data
}

export async function initSetup(data: SetupInitPayload) {
  const res = await apiClient.post('/api/v1/setup/init', data)
  return res.data
}

export async function listRoles() {
  const res = await apiClient.get('/api/v1/roles/')
  return res.data as Array<{ id: string; name: string; slug: string; description?: string; permissions: string[] }>
}
