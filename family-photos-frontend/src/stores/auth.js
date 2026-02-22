import { defineStore } from 'pinia';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    currentUser: JSON.parse(localStorage.getItem('family_user')) || null,
  }),
  actions: {
    login(user) {
      this.currentUser = user;
      localStorage.setItem('family_user', JSON.stringify(user));
    },
    logout() {
      this.currentUser = null;
      localStorage.removeItem('family_user');
    }
  }
});
