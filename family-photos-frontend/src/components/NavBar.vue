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
      <button class="nav-icon-btn" @click="router.push('/messages')" title="Messages">
        💬
        <span v-if="messaging.unreadTotal > 0" class="unread-dot">{{ badgeText }}</span>
      </button>

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
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { useMessagingStore } from '../stores/messaging';

const auth = useAuthStore();
const messaging = useMessagingStore();
const router = useRouter();
const particles = ref([]);

const badgeText = computed(() =>
  messaging.unreadTotal > 99 ? '99+' : messaging.unreadTotal
);

const currentTheme = computed(() => {
  const month = new Date().getMonth();
  if (month >= 2 && month <= 4) return 'theme-spring';
  if (month >= 5 && month <= 7) return 'theme-summer';
  if (month >= 8 && month <= 10) return 'theme-halloween';
  return 'theme-winter';
});

const refreshFeed = () => {
  if (router.currentRoute.value.path === '/home') {
    // This tells the browser to dispatch a custom event
    window.dispatchEvent(new CustomEvent('refresh-home-data'));
  } else {
    router.push('/home');
  }
};

onMounted(() => {
  // Generate 10-12 emojis specifically for the navbar width
  particles.value = Array.from({ length: 12 }).map(() => ({
    left: `${Math.random() * 100}%`,
    animationDuration: `${Math.random() * 3 + 2}s`,
    animationDelay: `${Math.random() * 5}s`
  }));

  // NavBar is mounted for the whole authenticated session, so this is
  // where the shared conversations/WebSocket state gets started; init()
  // is a no-op if Messages.vue (or a prior mount) already did it.
  messaging.init();
});

const returnToProfiles = () => {
  messaging.reset();
  auth.logout();
  window.location.href = '/';
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

.nav-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nav-icon-btn {
  position: relative;
  background: none;
  border: none;
  font-size: 1.3rem;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 4px;
  transition: background 0.3s;
}

.nav-icon-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.unread-dot {
  position: absolute;
  top: 0;
  right: 0;
  background: var(--accent, #e50914);
  color: white;
  font-size: 0.65rem;
  font-weight: 700;
  line-height: 1;
  border-radius: 999px;
  min-width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  box-shadow: 0 0 0 2px #141414;
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
