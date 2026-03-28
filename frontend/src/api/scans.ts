import apiClient from './client'
import type { Scan, CreateScanPayload } from '../types'

interface ScanListResponse {
  total: number
  scans: Scan[]
}

export interface ScanStatusData {
  id: string
  status: string
  progress_percentage: number
  current_phase: string
  vulnerabilities_found: number
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

export const listScans = (params?: { status?: string; limit?: number; offset?: number }) =>
  apiClient.get<ScanListResponse>('/api/v1/scans', { params })

export const createScan = (payload: CreateScanPayload) =>
  apiClient.post<Scan>('/api/v1/scans', payload)

export const getScan = (id: string) => apiClient.get<Scan>(`/api/v1/scans/${id}`)

export const getScanStatus = (id: string) => apiClient.get<ScanStatusData>(`/api/v1/scans/${id}/status`)

export const cancelScan = (id: string) => apiClient.post<Scan>(`/api/v1/scans/${id}/cancel`)

export const deleteScan = (id: string) => apiClient.delete(`/api/v1/scans/${id}`)
