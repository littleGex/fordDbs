// stores/auth.js
import { defineStore } from 'pinia';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    currentUser: JSON.parse(localStorage.getItem('user')) || null,
  }),
  actions: {
    login(user) {
      this.currentUser = user;
      localStorage.setItem('user', JSON.stringify(user));
    },
    updateUser(newData) {
      if (this.currentUser) {
        this.currentUser = { ...this.currentUser, ...newData };
        localStorage.setItem('user', JSON.stringify(this.currentUser));
      }
    },
    logout() {
      this.currentUser = null;
      localStorage.removeItem('user');
      localStorage.removeItem('token'); // <-- CRITICAL FIX: Add this line
    }
  }
});
