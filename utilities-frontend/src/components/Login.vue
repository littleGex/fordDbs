<template>
  <div class="min-h-screen bg-gray-50 flex items-center justify-center p-4">
    <div class="bg-white w-full max-w-sm p-8 rounded-2xl shadow-sm border border-gray-100">
      <h1 class="text-3xl font-extrabold text-gray-900 tracking-tight">Utility Dashboard</h1>
      <p class="text-sm text-gray-500 mt-1 mb-6">Parents only. Who are you?</p>

      <div class="grid grid-cols-2 gap-3 mb-6">
        <button
            v-for="u in users"
            :key="u.id"
            @click="selectedUserId = u.id"
            :class="['py-2.5 rounded-xl font-semibold transition-all',
                     selectedUserId === u.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700']"
        >
          {{ u.display_name }}
        </button>
      </div>

      <form v-if="selectedUserId" @submit.prevent="submit" class="space-y-3">
        <input v-model="password" type="password" placeholder="Password"
               autocomplete="current-password"
               class="w-full px-4 py-2.5 rounded-xl border border-gray-200 outline-none focus:border-blue-600">
        <button type="submit" :disabled="loading || !password"
                class="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white px-5 py-2.5 rounded-xl font-semibold shadow-sm transition-all">
          Log in
        </button>
      </form>

      <p v-if="errorMessage" class="text-red-600 font-semibold mt-4">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<script setup>
import {ref, onMounted} from 'vue';
import axios from 'axios';
import {AUTH_BASE, PARENT_ROLES, setSession} from '../auth';

const users = ref([]);
const selectedUserId = ref(null);
const password = ref('');
const errorMessage = ref('');
const loading = ref(false);

const fetchUsers = async () => {
  try {
    const res = await axios.get(`${AUTH_BASE}/login-options`, {params: {audience: 'parents'}});
    users.value = res.data;
  } catch (e) {
    errorMessage.value = "Could not load the family list. Please try again.";
  }
};

const submit = async () => {
  if (!selectedUserId.value || !password.value) return;
  loading.value = true;
  errorMessage.value = '';
  try {
    const res = await axios.post(`${AUTH_BASE}/login`, {
      user_id: selectedUserId.value,
      password: password.value
    });
    if (!PARENT_ROLES.includes(res.data.user.role)) {
      errorMessage.value = "Parents only";
      return;
    }
    setSession(res.data.access_token, res.data.user);
  } catch (e) {
    // 403 and 429 carry the reason, e.g. an account still waiting for
    // approval, or too many wrong passwords
    if (e.response?.status === 401) {
      errorMessage.value = "Wrong password!";
    } else if ([403, 429].includes(e.response?.status)) {
      errorMessage.value = e.response.data.detail;
    } else {
      errorMessage.value = "Login failed. Please try again.";
    }
  } finally {
    password.value = '';
    loading.value = false;
  }
};

onMounted(fetchUsers);
</script>
