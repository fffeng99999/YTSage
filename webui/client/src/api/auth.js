/**
 * Auth API
 */
import api from './http'

export function login(password) {
  return api.post('/auth/login', { password }).then((r) => r.data)
}

export function verifyToken() {
  return api.get('/auth/verify').then((r) => r.data)
}

export function changePassword(currentPassword, newPassword) {
  return api.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  }).then((r) => r.data)
}
