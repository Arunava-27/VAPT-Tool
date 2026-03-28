import apiClient from './client'
import type { User } from '../types'

export interface LoginResponse {
  access_token: string
  refresh_token?: string
  token_type: string
}

export const login = (email: string, password: string) =>
  apiClient.post<LoginResponse>('/api/v1/auth/login', { email, password })

export const refreshToken = (token: string) =>
  apiClient.post<LoginResponse>('/api/v1/auth/refresh', { refresh_token: token })

export const getMe = () => apiClient.get<User>('/api/v1/auth/me')

export const logoutApi = () => apiClient.post('/api/v1/auth/logout')
