import apiClient from './client'
import type { Scan, CreateScanPayload } from '../types'

export const listScans = (params?: { status?: string; limit?: number; offset?: number }) =>
  apiClient.get<Scan[]>('/api/v1/scans', { params })

export const createScan = (payload: CreateScanPayload) =>
  apiClient.post<Scan>('/api/v1/scans', payload)

export const getScan = (id: string) => apiClient.get<Scan>(`/api/v1/scans/${id}`)

export const getScanStatus = (id: string) => apiClient.get<Scan>(`/api/v1/scans/${id}/status`)

export const cancelScan = (id: string) => apiClient.delete<Scan>(`/api/v1/scans/${id}`)
