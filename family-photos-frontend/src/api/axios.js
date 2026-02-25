import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE,
});

// Remove default JSON header completely
delete api.defaults.headers.post['Content-Type'];

export default api;
