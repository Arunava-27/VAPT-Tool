import apiClient from './client'

export interface AnalyzeRequest {
  scan_id?: string
  target: string
  scan_type?: string
  available_tools?: string[]
}

export interface AnalyzeJob {
  job_id: string
  status: 'running' | 'completed' | 'failed'
  result?: Record<string, unknown>
}

export const startAnalysis = (payload: AnalyzeRequest) =>
  apiClient.post<AnalyzeJob>('/api/v1/ai/analyze', payload)

export const getAnalysisStatus = (jobId: string) =>
  apiClient.get<AnalyzeJob>(`/api/v1/ai/analyze/${jobId}`)

export const getAiHealth = () => apiClient.get('/api/v1/ai/health')
