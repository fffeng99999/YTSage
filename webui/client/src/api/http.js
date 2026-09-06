/**
 * Axios instance with auth interceptor + i18n-aware error extraction.
 */
import axios from 'axios'
import router from '@/router'
import i18n from '@/i18n'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Request interceptor - add token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('ytsage_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor - handle 401
api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('ytsage_token')
      router.push('/login')
    }
    return Promise.reject(err)
  }
)

/**
 * Backend returns some error `detail`s as i18n keys
 * (e.g. "url_validation.empty_url", "ytdlp_errors.private_video").
 * Translate when the key exists in messages, else return raw text.
 */
export function errText(err, fallbackKey = 'errors.generic_error') {
  const detail = err?.response?.data?.detail
  if (!detail) return err?.message || String(err)
  if (typeof detail === 'string' && i18n.global.te(detail)) {
    return i18n.global.t(detail)
  }
  if (typeof detail === 'string' && detail.startsWith('errors.')) {
    return i18n.global.t('errors.generic_error', { error: detail })
  }
  return detail
}

export default api
