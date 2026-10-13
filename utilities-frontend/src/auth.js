import {reactive, computed} from 'vue'

export const API_BASE = import.meta.env.VITE_API_BASE;
// Logins are shared with Fordstagram, which lives next to utilities
export const AUTH_BASE = API_BASE.replace(/\/utilities\/?$/, '/family-photos');

export const PARENT_ROLES = ['parent', 'admin']

const readUser = () => {
  try {
    return JSON.parse(localStorage.getItem('user'))
  } catch (e) {
    return null
  }
}

export const auth = reactive({
  token: localStorage.getItem('token'),
  user: readUser()
})

export const isLoggedIn = computed(() => !!auth.token && !!auth.user)

export const setSession = (token, user) => {
  auth.token = token
  auth.user = user
  localStorage.setItem('token', token)
  localStorage.setItem('user', JSON.stringify(user))
}

export const setToken = (token) => {
  auth.token = token
  localStorage.setItem('token', token)
}

export const logout = () => {
  auth.token = null
  auth.user = null
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  // Left over from the old shared admin password
  localStorage.removeItem('admin_token')
}
