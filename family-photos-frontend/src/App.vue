<template>
  <div class="app-container">
    <ProfilePicker v-if="!auth.currentUser" />
    <div v-else>
      <nav>
        <span>Logged in as: {{ auth.currentUser.display_name }}</span>
        <button @click="auth.logout()">Switch User</button>
      </nav>
      <UserProfile />
    </div>
  </div>
</template>

<script setup>
import ProfilePicker from './views/ProfilePicker.vue';
import UserProfile from './views/UserProfile.vue';
import { useAuthStore } from './stores/auth';

const auth = useAuthStore();
</script>
