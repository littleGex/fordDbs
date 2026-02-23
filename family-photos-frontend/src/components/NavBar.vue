<template>
  <nav v-if="auth.currentUser">
    <div class="nav-left">
      <h2 class="nav-logo" @click="goHome">FORDSTAGRAM</h2>
    </div>

    <div class="nav-right">
      <div class="nav-user-info">
        <span>{{ auth.currentUser.display_name }}</span>
        <img
          :src="auth.currentUser.profile_photo_url || '/avatars/default.png'"
          class="nav-avatar"
          @click="toggleDropdown"
        />
        <button @click="handleLogout" class="logout-link">Logout</button>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();

const goHome = () => {
  // If you use Vue Router: router.push('/')
  // If you are using conditional rendering:
  // auth.currentUser stays, but we tell the parent to show the feed
};

const handleLogout = () => {
  if (confirm("Are you sure you want to log out?")) {
    auth.logout();
    // This will automatically trigger the ProfilePicker
    // to show up because auth.currentUser becomes null
  }
};
</script>

<style scoped>
.nav-logo {
  color: #e50914; /* Netflix Red */
  cursor: pointer;
  letter-spacing: 2px;
  font-size: 1.5rem;
  margin: 0;
}

.nav-avatar {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  cursor: pointer;
}

.logout-link {
  background: none;
  border: none;
  color: #b3b3b3;
  cursor: pointer;
  font-size: 0.8rem;
  text-decoration: underline;
}

.logout-link:hover {
  color: white;
}
</style>
