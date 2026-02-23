<template>
  <div id="app">
    <NavBar v-if="auth.currentUser" />

    <main>
      <ProfilePicker v-if="!auth.currentUser" />
      <UserProfile v-else />
    </main>
  </div>
</template>

<script setup>
import NavBar from './components/NavBar.vue';
import ProfilePicker from './components/ProfilePicker.vue';
import UserProfile from './views/UserProfile.vue';
import { useAuthStore } from './stores/auth';

const auth = useAuthStore();
</script>

<style>
main {
  /* This ensures the content starts below the sticky NavBar */
  padding-top: 20px;
  min-height: calc(100vh - 70px);
}
</style>
