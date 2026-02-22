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
        <img :src="getProfileImage(user)" :alt="user.display_name" class="avatar" />
        <h3>{{ user.display_name }}</h3>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios';
import { useAuthStore } from '../stores/auth'; //

const auth = useAuthStore();
const users = ref([]);

onMounted(async () => {
  try {
    // Calling http://ford-home-pi.local:8005/v1/family-photos/users
    const response = await api.get('/users');
    users.value = response.data;
  } catch (error) {
    console.error("Failed to fetch users", error);
  }
});

const selectUser = (user) => {
  auth.login(user); // Sets localStorage and currentUser
};

function getProfileImage(user) {
  // Uses the signed MinIO URL from the backend
  return user.profile_photo_url || '/avatars/default.png';
}
</script>
