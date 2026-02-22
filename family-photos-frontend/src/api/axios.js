import axios from 'axios';

const api = axios.create({
  // Point this to your backend API port from docker-compose
  baseURL: import.meta.env.VITE_API_URL || 'https://api-pocket-money.ford-home-apps.com/v1',
  headers: {
    'Content-Type': 'application/json',
  }
});

export default api;
