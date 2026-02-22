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
        <img :src="getCleanImageUrl(user)" class="avatar" />
        <h3>{{ user.display_name }}</h3>
        <p v-if="user.bio" class="bio-preview">{{ user.bio }}</p>
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
  if (!user.profile_photo_url) return '/avatars/default.png';
  // Use the logic that worked earlier to strip signatures
  const match = user.profile_photo_url.match(/\/([^/?#]+)[^/]*$/);
  const fileName = match ? match[1] : 'default.png';
  return `http://ford-home-pi.local:9000/family-photos/avatars/${fileName}`;
}
</script>
