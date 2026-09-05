import axios from 'axios';
import { useAuthStore } from '../stores/auth';

// VITE_API_BASE is baked in at build time pointing at .../v1/family-photos
// (see docker-compose.yaml / .env) -- the messaging service lives at the
// sibling .../v1/messaging path on the same API.
const FAMILY_PHOTOS_BASE = import.meta.env.VITE_API_BASE;
export const MESSAGING_BASE = FAMILY_PHOTOS_BASE.replace(
  /\/family-photos\/?$/, '/messaging'
);
export const MESSAGING_WS_BASE = MESSAGING_BASE.replace(/^http/, 'ws');

const messagingApi = axios.create({
  baseURL: MESSAGING_BASE,
  timeout: 15000,
});

messagingApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Unlike api/axios.js, this doesn't attempt a silent token refresh on 401
// -- tokens are long-lived (24h, see family_photos.py's login()) so mid-chat
// expiry is rare, and it isn't worth duplicating that request-queueing
// dance for a second axios instance. Just send the user back to login.
messagingApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const auth = useAuthStore();
      auth.logout();
      import('../router/index').then(m => m.default.push({ name: 'login' }));
    }
    return Promise.reject(error);
  }
);

delete messagingApi.defaults.headers.post['Content-Type'];
export default messagingApi;
