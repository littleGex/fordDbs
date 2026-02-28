<template>
  <nav v-if="auth.currentUser" :class="['main-nav', currentTheme]">
    <div class="seasonal-overlay">
      <div
        v-for="(style, index) in particles"
        :key="index"
        class="particle"
        :style="style"
      ></div>
    </div>

    <div class="nav-left">
      <h2 class="nav-logo" @click="refreshFeed">FORDSTAGRAM</h2>
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
import { ref, onMounted, computed } from 'vue';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const particles = ref([]);

const currentTheme = computed(() => {
  const month = new Date().getMonth();
  if (month >= 2 && month <= 4) return 'theme-spring';
  if (month >= 5 && month <= 7) return 'theme-summer';
  if (month >= 8 && month <= 10) return 'theme-halloween';
  return 'theme-winter';
});

const refreshFeed = () => {
  // If you want a hard refresh:
  window.location.reload();
  // OR if you want to just tell UserProfile to fetch photos again:
  // emit('refresh');
};

onMounted(() => {
  // Generate 10-12 emojis specifically for the navbar width
  particles.value = Array.from({ length: 12 }).map(() => ({
    left: `${Math.random() * 100}%`,
    animationDuration: `${Math.random() * 3 + 2}s`,
    animationDelay: `${Math.random() * 5}s`
  }));
});

const returnToProfiles = () => {
  // Simply clearing the user sends them back to the ProfilePicker
  // because of the v-if logic in App.vue
  auth.logout();
};
</script>

<style scoped>
.nav-logo {
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
