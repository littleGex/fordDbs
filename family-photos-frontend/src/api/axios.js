import axios from 'axios';

const api = axios.create({
  // Vite uses import.meta.env to access .env variables
  baseURL: import.meta.env.VITE_API_BASE,
  headers: {
    'Content-Type': 'application/json',
  }
});

export default api;
