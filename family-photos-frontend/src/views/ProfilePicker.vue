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
          v-if="user"
          :src="getCleanImageUrl(user)"
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
    users.value = response.data;
  } catch (error) {
    console.error("Failed to fetch users", error);
  }
});

const selectUser = (user) => {
  auth.login(user);
};

function getCleanImageUrl(user) {
  // 1. If we have no URL at all, use a fallback
  if (!user.profile_photo_url) return '/avatars/default.png';

  // 2. Extract the base filename (e.g., bear.png) from the long signed URL
  // This regex grabs everything between the last '/' and the '?'
  const match = user.profile_photo_url.match(/\/([^/?#]+)[^/]*$/);
  const fileName = match ? match[1] : 'default.png';

  // 3. Return the direct, unsigned path to your now-public MinIO folder
  return `http://ford-home-pi.local:9000/family-photos/avatars/${fileName}`;
}
</script>
