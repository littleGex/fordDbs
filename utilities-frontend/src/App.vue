<template>
  <Dashboard />
</template>

<script setup>
import Dashboard from './views/Dashboard.vue'
</script>

<style>
/* Add Tailwind imports in your main.css, but standard resets here */
body {
  @apply bg-gray-50;
  margin: 0;
  font-family: 'Inter', sans-serif;
}
</style>
