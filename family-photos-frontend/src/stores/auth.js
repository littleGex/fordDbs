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
    // The missing piece:
    updateUser(newData) {
      if (this.currentUser) {
        // We spread the existing data and overwrite with the new updates
        this.currentUser = { ...this.currentUser, ...newData };
        localStorage.setItem('user', JSON.stringify(this.currentUser));
      }
    },
    logout() {
      this.currentUser = null;
      localStorage.removeItem('user');
    }
  }
});
