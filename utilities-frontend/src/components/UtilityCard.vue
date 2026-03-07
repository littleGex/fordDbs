<template>
  <div class="p-6 bg-white rounded-xl shadow-sm border border-gray-100">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider">{{ title }}</h3>
      <span class="text-2xl">{{ title === 'Water' ? '💧' : title === 'Gas' ? '🔥' : '⚡' }}</span>
    </div>

    <div class="flex items-baseline space-x-2">
      <span class="text-2xl font-bold text-gray-900">{{ value }}</span>
      <span class="text-sm text-gray-500">{{ unit }}</span>
    </div>

    <div v-if="usage !== undefined" class="mt-4 flex items-center">
      <span :class="usage > 0 ? 'text-red-500' : 'text-green-500'" class="text-sm font-semibold flex items-center">
        <template v-if="usage > 0">▲</template>
        <template v-else>▼</template>
        {{ Math.abs(usage) }} {{ unit }} usage
      </span>
      <span class="ml-2 text-xs text-gray-400 text-nowrap">vs last month</span>
    </div>
  </div>
</template>

<script setup>
defineProps(['title', 'value', 'unit', 'usage', 'icon']);
</script>
