<template>
  <div class="admin-accounts">
    <h2 class="section-title">Waiting for approval</h2>

    <div v-if="accounts.pending.length === 0" class="empty-state">
      No requests waiting.
    </div>

    <div v-for="user in accounts.pending" :key="user.id" class="account-row">
      <img :src="getAvatar(user)" class="account-avatar" />
      <span class="account-name">{{ user.display_name }}</span>
      <select v-model="user.role" class="role-select">
        <option value="child">Child</option>
        <option value="adult">Adult</option>
      </select>
      <button class="btn-primary" @click="approve(user)">Approve</button>
      <button class="btn-secondary" @click="reject(user)">Reject</button>
    </div>

    <h2 class="section-title">Family</h2>

    <div v-for="user in family" :key="user.id" class="account-row">
      <img :src="getAvatar(user)" class="account-avatar" />
      <span class="account-name">{{ user.display_name }}</span>
      <span v-if="user.role === 'admin'" class="role-label">Admin</span>
      <select
        v-else
        :value="user.role"
        class="role-select"
        @change="changeRole(user, $event.target.value)"
      >
        <option value="child">Child</option>
        <option value="adult">Adult</option>
        <option value="parent">Parent</option>
      </select>
      <button class="btn-secondary" @click="resetTarget = user">Reset password</button>
    </div>

    <div v-if="resetTarget" class="modal-overlay" @click.self="closeReset">
      <div class="modal-content">
        <h2>Reset Password</h2>
        <p>Profile: {{ resetTarget.display_name }}</p>
        <input
          v-model="newPassword"
          type="password"
          placeholder="New password"
          @keyup.enter="resetPassword"
          class="styled-input"
        />
        <div class="modal-btns">
          <button @click="closeReset" class="btn-secondary">Cancel</button>
          <button @click="resetPassword" class="btn-primary" :disabled="!newPassword">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios.js';
import { useAccountsStore } from '../stores/accounts.js';
import { getAvatar } from '../utils/avatar.js';

const accounts = useAccountsStore();
const family = ref([]);
const resetTarget = ref(null);
const newPassword = ref('');

const fetchFamily = async () => {
  try {
    const res = await api.get('/users');
    family.value = res.data;
  } catch (err) {
    console.error('Failed to fetch family', err);
  }
};

const refresh = () => Promise.all([accounts.fetchPending(), fetchFamily()]);

const failed = (action, err) =>
  alert(`${action} failed: ` + (err.response?.data?.detail || 'Check console'));

const approve = async (user) => {
  try {
    await api.post(`/admin/users/${user.id}/approve`, { role: user.role });
    await refresh();
  } catch (err) {
    failed('Approval', err);
  }
};

const reject = async (user) => {
  if (!confirm(`Reject and delete the request from ${user.display_name}?`)) return;
  try {
    await api.post(`/admin/users/${user.id}/reject`);
    await refresh();
  } catch (err) {
    failed('Rejection', err);
  }
};

const changeRole = async (user, role) => {
  try {
    await api.post(`/admin/users/${user.id}/role`, { role });
  } catch (err) {
    failed('Role change', err);
  }
  await fetchFamily();
};

const closeReset = () => {
  resetTarget.value = null;
  newPassword.value = '';
};

const resetPassword = async () => {
  if (!newPassword.value) return;
  try {
    await api.post(`/admin/users/${resetTarget.value.id}/reset-password`, {
      password: newPassword.value
    });
    closeReset();
  } catch (err) {
    failed('Password reset', err);
  }
};

onMounted(refresh);
</script>

<style scoped>
.admin-accounts {
  max-width: 700px;
  margin: 0 auto;
  padding: 20px;
}

.section-title {
  margin: 30px 0 15px;
}

.empty-state {
  color: #808080;
  font-style: italic;
}

.account-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px;
  margin-bottom: 8px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
}

.account-avatar {
  width: 44px;
  height: 44px;
  border-radius: 6px;
  object-fit: cover;
}

.account-name {
  flex: 1;
  min-width: 100px;
  font-weight: 600;
}

.role-select {
  background: #2b2b2b;
  color: white;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 8px;
}

.role-label {
  color: #808080;
  padding: 8px;
}

.styled-input {
  width: 100%;
  padding: 12px;
  margin: 12px 0;
  background: #333;
  border: 1px solid #444;
  border-radius: 4px;
  color: white;
  box-sizing: border-box;
}
</style>
