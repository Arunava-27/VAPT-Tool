import apiClient from './client'

export interface Report {
  id: string
  scan_id: string
  title: string
  report_type: 'full' | 'executive' | 'technical'
  status: 'generating' | 'ready' | 'failed'
  format: 'json' | 'html'
  created_at: string
}

export interface GenerateReportRequest {
  scan_id: string
  format: 'html' | 'json'
  report_type: 'full' | 'executive' | 'technical'
  title?: string
}

export const generateReport = (data: GenerateReportRequest) =>
  apiClient.post<Report>('/reports/generate', data)

export const listReports = (scan_id?: string) =>
  apiClient.get<Report[]>('/reports/', { params: scan_id ? { scan_id } : {} })

export const downloadReport = async (reportId: string, format: string) => {
  const response = await apiClient.get(`/reports/${reportId}/download`, {
    responseType: format === 'html' ? 'blob' : 'json',
  })
  return response
}

export const deleteReport = (reportId: string) =>
  apiClient.delete(`/reports/${reportId}`)
