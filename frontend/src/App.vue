<script setup>
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const isAdmin = ref(false)

// We watch the "route" object.
// Every time you move between pages, this code runs.
watch(() => route.path, () => {
  isAdmin.value = !!localStorage.getItem('admin_token')
}, { immediate: true })

const logout = () => {
  localStorage.removeItem('admin_token')
  isAdmin.value = false
  router.push('/')
}
</script>

<template>
  <div class="app-shell">
    <header class="main-header">
      <div class="logo">
        <h1>💰 Pocket Money Bank</h1>
      </div>
      <nav class="nav-links">
        <router-link to="/">Dashboard</router-link>
        <router-link to="/admin">Admin</router-link>
        <button v-if="isAdmin" @click="logout" class="btn-logout">Logout</button>
      </nav>
    </header>

    <main class="content-area">
      <router-view />
    </main>
  </div>
</template>

<style>
/* Global Styles */
body { margin: 0; background: #f4f7f6; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }

.main-header {
  background: #2d3436;
  color: white;
  padding: 1rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.nav-links { display: flex; align-items: center; gap: 20px; }
.nav-links a { color: #b2bec3; text-decoration: none; font-weight: bold; transition: 0.3s; }
.nav-links a.router-link-active { color: #4a90e2; }

.btn-logout {
  background: #ff4757;
  color: white;
  border: none;
  padding: 8px 15px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: bold;
}

.content-area { padding: 20px; max-width: 1200px; margin: 0 auto; }
</style>
