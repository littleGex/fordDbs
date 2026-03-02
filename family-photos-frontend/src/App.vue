<template>
  <div id="app">
    <div v-if="isInitializing" class="initial-loader">
      <div class="spinner"></div>
      <p>Loading Family Moments...</p>
    </div>

    <template v-else>
      <NavBar v-if="auth.currentUser" />

      <main :class="{ 'no-nav': !auth.currentUser }">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import NavBar from './components/NavBar.vue';
import { useAuthStore } from './stores/auth'; //

const auth = useAuthStore();
const isInitializing = ref(true);

onMounted(() => {
  // A small 300ms delay ensures Pinia has hydrated and the Router guard has finished
  // checking the token before we reveal the UI.
  setTimeout(() => {
    isInitializing.value = false;
  }, 300);
});
</script>

<style>
/* --- App Layout --- */
main {
  /* Offset for sticky NavBar */
  padding-top: 20px;
  min-height: calc(100vh - 70px);
  transition: padding 0.3s ease;
}

main.no-nav {
  padding-top: 0;
}

/* --- Initial Loader Styles --- */
.initial-loader {
  height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #141414; /* Match your app background */
  color: white;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(255, 255, 255, 0.1);
  border-left-color: #e50914; /* Your brand color */
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 20px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* --- Page Transition Animations --- */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
