import axios from 'axios';
import { useAuthStore } from '../stores/auth'; // Adjust path if necessary

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
});

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    // Access the store inside the function to ensure Pinia is initialized
    const auth = useAuthStore();

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise(function(resolve, reject) {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        }).catch(err => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const res = await axios.post(`${import.meta.env.VITE_API_BASE}/refresh`, {}, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        });

        if (res.data.access_token) {
          const newToken = res.data.access_token;
          localStorage.setItem('token', newToken);
          processQueue(null, newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        }
      } catch (refreshError) {
        processQueue(refreshError, null);

        auth.logout();

        // Use the router to redirect to login smoothly
        import('../router/index').then(m => m.default.push({ name: 'login' }));
      } finally {
        isRefreshing = false; // RELEASE THE LOCK
      }
    }
    return Promise.reject(error);
  }
);

delete api.defaults.headers.post['Content-Type'];
export default api;
