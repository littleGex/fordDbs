<template>
  <div class="profile-picker">
    <h1>Who's watching?</h1>
    <div class="user-grid">
      <div
        v-for="user in users"
        :key="user.id"
        class="profile-card"
        @click="selectUser(user)"
      >
        <img
          v-if="user.profile_photo_key"
          :src="'/' + user.profile_photo_key"
          :alt="user.display_name"
          class="avatar"
        />
        <h3>{{ user.display_name }}</h3>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const users = ref([]);

onMounted(async () => {
  try {
    const response = await api.get('/users');
    // Log this to your console to see the exact property names
    console.log("Backend Users:", response.data);
    users.value = response.data;
  } catch (error) {
    console.error("Failed to fetch users", error);
  }
});

const selectUser = (user) => {
  auth.login(user);
};
</script>
