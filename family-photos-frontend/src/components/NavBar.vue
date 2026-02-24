<template>
  <nav v-if="auth.currentUser">
    <div class="nav-left">
      <h2 class="nav-logo" @click="refreshFeed" title="Refresh Feed">
        FORDSTAGRAM
      </h2>
    </div>

    <div class="nav-right">
      <div class="nav-user-info" @click="returnToProfiles" title="Switch Profile">
        <span>{{ auth.currentUser.display_name }}</span>
        <img
          :src="auth.currentUser.profile_photo_url || '/avatars/default.png'"
          class="nav-avatar"
        />
        <span class="switch-icon">⇄</span>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();

const refreshFeed = () => {
  // If you want a hard refresh:
  window.location.reload();
  // OR if you want to just tell UserProfile to fetch photos again:
  // emit('refresh');
};

const returnToProfiles = () => {
  // Simply clearing the user sends them back to the ProfilePicker
  // because of the v-if logic in App.vue
  auth.logout();
};
</script>

<style scoped>
.nav-logo {
  color: #e50914;
  cursor: pointer;
  transition: transform 0.1s;
}
.nav-logo:active {
  transform: scale(0.95);
}

.nav-user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  padding: 5px 10px;
  border-radius: 4px;
  transition: background 0.3s;
}

.nav-user-info:hover {
  background: rgba(255, 255, 255, 0.1);
}

.switch-icon {
  font-size: 0.8rem;
  opacity: 0.6;
}

.nav-avatar {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  object-fit: cover;
}
</style>
