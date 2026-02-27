// axios.js
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
});

// Request Interceptor (Existing)
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response Interceptor (New Silent Refresh Logic)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Check if error is 401 and we haven't tried to refresh this specific request yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Call the new refresh endpoint
        // Note: We use the base axios here to avoid an infinite loop
        const res = await axios.post(`${import.meta.env.VITE_API_BASE}/refresh`, {}, {
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        });

        if (res.data.access_token) {
          const newToken = res.data.access_token;
          localStorage.setItem('token', newToken);

          // Update the header for the original failed request and retry it
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        }
      } catch (refreshError) {
        // If the refresh itself fails (e.g., token is totally invalid),
        // clear storage and send them to the profile picker
        localStorage.removeItem('token');
        window.location.href = '/';
      }
    }
    return Promise.reject(error);
  }
);

delete api.defaults.headers.post['Content-Type'];
export default api;
