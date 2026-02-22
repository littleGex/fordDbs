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
            :src="'http://ford-home-pi.local:9000/family-photos/' + user.profile_photo_key"
            class="avatar"
        />
        <h3>{{ user.display_name }}</h3>
      </div>
    </div>
  </div>
</template>

<script setup>
import {ref, onMounted} from 'vue';
import api from '../api/axios';
import {useAuthStore} from '../stores/auth';

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
</script>
