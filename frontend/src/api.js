import axios from 'axios'
import {API_BASE, AUTH_BASE, auth, setToken, logout} from './auth'

const api = axios.create({baseURL: API_BASE})

api.interceptors.request.use((config) => {
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

let refreshing = null

// Swap an expired token for a fresh one; shared so parallel 401s refresh once
const refreshToken = () => {
  if (!refreshing) {
    refreshing = axios.post(`${AUTH_BASE}/refresh`, {}, {
      headers: {Authorization: `Bearer ${auth.token}`}
    }).then((res) => {
      setToken(res.data.access_token)
      return res.data.access_token
    }).finally(() => {
      refreshing = null
    })
  }
  return refreshing
}

api.interceptors.response.use(
    (response) => response,
    async (error) => {
      const original = error.config
      if (error.response?.status !== 401 || original._retry || !auth.token) {
        return Promise.reject(error)
      }
      original._retry = true
      try {
        const token = await refreshToken()
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      } catch (refreshError) {
        logout()
        import('./router').then(m => m.default.push('/login'))
        return Promise.reject(refreshError)
      }
    }
)

export default api
