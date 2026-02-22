<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios';

const users = ref([]);
const defaultAvatars = [
  '/avatars/bear.png',
  '/avatars/cat.png',
  '/avatars/robot.png',
  '/avatars/panda.png',
  '/avatars/alien.png'
];

onMounted(async () => {
  try {
    const response = await api.get('/users');
    users.value = response.data;
  } catch (error) {
    console.error("Failed to fetch users", error);
  }
});

function getProfileImage(user) {
  // If user has a real photo in MinIO
  if (user.profile_photo_url) return user.profile_photo_url;

  // Fallback to a default based on their ID so it's consistent
  const defaultIdx = user.id % defaultAvatars.length;
  return defaultAvatars[defaultIdx];
}
</script>

<template>
  <div class="user-grid">
    <div v-for="user in users" :key="user.id" class="profile-card">
      <img :src="getProfileImage(user)" class="avatar" />
      <h3>{{ user.display_name }}</h3>
    </div>
  </div>
</template>
