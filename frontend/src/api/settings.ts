import apiClient from './client'

export interface CloudCredential {
  id: string
  provider: 'aws' | 'gcp' | 'azure'
  config: Record<string, string>  // masked values
  created_at: string
  updated_at: string
}

export const getCloudCredentials = () =>
  apiClient.get<CloudCredential[]>('/settings/cloud-credentials')

export const saveCloudCredential = (provider: string, config: Record<string, string>) =>
  apiClient.post('/settings/cloud-credentials', { provider, config })

export const deleteCloudCredential = (provider: string) =>
  apiClient.delete(`/settings/cloud-credentials/${provider}`)

export const testCloudCredential = (provider: string) =>
  apiClient.post(`/settings/cloud-credentials/${provider}/test`)

export const getHostAgentSettings = () =>
  apiClient.get('/settings/host-agent')

export const updateHostAgentUrl = (url: string) =>
  apiClient.post('/settings/host-agent', { url })
