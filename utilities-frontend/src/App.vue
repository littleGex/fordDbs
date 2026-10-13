<template>
  <Dashboard v-if="isLoggedIn" />
  <Login v-else />
</template>

<script setup>
import Dashboard from './views/Dashboard.vue'
import Login from './components/Login.vue'
import { isLoggedIn } from './auth'
</script>
