import apiClient from './client'

export interface CloudCredential {
  id: string
  provider: 'aws' | 'gcp' | 'azure'
  credentials: Record<string, string>  // masked values
  created_at: string
  updated_at: string
}

export const getCloudCredentials = () =>
  apiClient.get<CloudCredential[]>('/api/v1/settings/cloud-credentials')

export const saveCloudCredential = (provider: string, credentials: Record<string, string>) =>
  apiClient.post('/api/v1/settings/cloud-credentials', { provider, credentials })

export const deleteCloudCredential = (provider: string) =>
  apiClient.delete(`/api/v1/settings/cloud-credentials/${provider}`)

export const testCloudCredential = (provider: string) =>
  apiClient.post(`/api/v1/settings/cloud-credentials/${provider}/test`)

export const getHostAgentSettings = () =>
  apiClient.get('/api/v1/settings/host-agent')

export const updateHostAgentUrl = (url: string) =>
  apiClient.post('/api/v1/settings/host-agent', { url })

export const getPlatformSettings = () =>
  apiClient.get('/api/v1/settings/platform')
