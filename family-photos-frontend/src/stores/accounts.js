// stores/accounts.js
import { defineStore } from 'pinia';
import api from '../api/axios';

// Account requests waiting for the admin; drives the NavBar badge
export const useAccountsStore = defineStore('accounts', {
  state: () => ({
    pending: [],
  }),
  getters: {
    pendingCount: (state) => state.pending.length,
  },
  actions: {
    async fetchPending() {
      try {
        const res = await api.get('/admin/pending');
        this.pending = res.data;
      } catch (err) {
        console.error('Failed to fetch pending accounts', err);
      }
    },
    reset() {
      this.pending = [];
    }
  }
});
