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

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse {
  response: string
  provider: string
  model: string
  latency_ms: number
  is_cpu_only?: boolean
  estimated_wait_seconds?: number
  queue_depth?: number
}

export interface AiInfo {
  status: string
  active_provider?: string
  active_model?: string
  available_providers?: string[]
  ollama_url?: string
  is_cpu_only?: boolean
  estimated_wait_seconds?: number
  concurrency_limit?: number
  queue_depth?: number
  cpu_warning?: string
  max_tokens?: number
  agent_timeout_seconds?: number
}

export interface ModelList {
  provider: string
  current_model: string
  models: string[]
  ollama_url: string
  is_cpu_only?: boolean
  error?: string
}

export interface QueueStatus {
  queue_depth: number
  concurrency_limit: number
  is_cpu_only: boolean
  active_model: string
  estimated_wait_seconds: number | null
}

export const startAnalysis = (payload: AnalyzeRequest) =>
  apiClient.post<AnalyzeJob>('/api/v1/ai/analyze', payload)

export const getAnalysisStatus = (jobId: string) =>
  apiClient.get<AnalyzeJob>(`/api/v1/ai/analyze/${jobId}`)

export const getAiHealth = () => apiClient.get('/api/v1/ai/health')

export const getAiInfo = () => apiClient.get<AiInfo>('/api/v1/ai/info')

export const listModels = () => apiClient.get<ModelList>('/api/v1/ai/models')

export const getQueueStatus = () => apiClient.get<QueueStatus>('/api/v1/ai/queue')

export const listAnalyses = () => apiClient.get<AnalyzeJob[]>('/api/v1/ai/analyses')

export const sendChat = (message: string, context?: string, history?: ChatMessage[]) =>
  apiClient.post<ChatResponse>('/api/v1/ai/chat', { message, context, history })

export const updateAiConfig = (model?: string, provider?: string) =>
  apiClient.patch<{ ok: boolean; active_provider: string; active_model: string; is_cpu_only: boolean; estimated_wait_seconds: number | null }>(
    '/api/v1/ai/config',
    { model, provider }
  )

