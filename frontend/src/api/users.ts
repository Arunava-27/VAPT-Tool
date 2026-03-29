import apiClient from './client'

export interface ProfileUpdatePayload {
  full_name?: string
  email?: string
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
  confirm_password: string
}

export async function updateProfile(data: ProfileUpdatePayload) {
  const res = await apiClient.patch('/api/v1/users/me', data)
  return res.data
}

export async function changePassword(data: ChangePasswordPayload) {
  await apiClient.post('/api/v1/users/me/password', data)
}
