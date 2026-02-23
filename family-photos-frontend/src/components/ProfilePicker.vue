<template>
  <div class="profile-picker">
    <h1>Who's watching?</h1>
    <div v-if="users.length === 0" class="loading">Loading profiles...</div>
    <div v-else class="user-grid">
      <div
        v-for="user in users"
        :key="user.id"
        class="profile-card"
        @click="selectUser(user)"
      >
        <img
          :src="user.profile_photo_url || '/avatars/default.png'"
          class="avatar"
          @error="(e) => e.target.src = '/avatars/default.png'"
        />
        <h3>{{ user.display_name }}</h3>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios.js';
import { useAuthStore } from '../stores/auth.js';

const auth = useAuthStore();
const users = ref([]);

onMounted(async () => {
  try {
    // Hits @family_photos_router.get("/users")
    const response = await api.get('/users');
    users.value = response.data;
  } catch (error) {
    console.error("Failed to fetch users", error);
  }
});

const selectUser = (user) => {
  // Sets the current user in the Pinia store
  auth.login(user);
};
</script>
