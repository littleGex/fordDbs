<template>
  <div class="p-6 bg-white rounded-xl shadow-sm border border-gray-100">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider">{{ title }}</h3>
      <span class="text-2xl">{{ emoji }}</span>
    </div>

    <div class="flex items-baseline space-x-2">
      <span class="text-2xl font-bold text-gray-900">{{ value ?? '---' }}</span>
      <span class="text-sm text-gray-500">{{ unit }}</span>
    </div>

    <div v-if="usage !== undefined" class="mt-4 flex items-center">
      <span
        :class="statusColor"
        class="text-sm font-semibold flex items-center"
      >
        <template v-if="usage > 0">▲</template>
        <template v-else-if="usage < 0">▼</template>
        {{ Math.abs(usage) }} {{ unit }}
      </span>
      <span class="ml-2 text-xs text-gray-400 text-nowrap">vs last month</span>

      <span v-if="isReset" class="ml-auto bg-amber-100 text-amber-700 text-[10px] px-2 py-0.5 rounded-full font-bold uppercase">
        New Meter
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
const props = defineProps(['title', 'value', 'unit', 'usage', 'isInverse', 'isReset']);

const emoji = computed(() => {
  if (props.title.includes('Water')) return '💧';
  if (props.title.includes('Gas')) return '🔥';
  return '⚡';
});

const statusColor = computed(() => {
  if (!props.usage) return 'text-gray-500';
  const isPositive = props.usage > 0;

  if (props.isInverse) {
    return isPositive ? 'text-green-500' : 'text-red-500';
  }
  return isPositive ? 'text-red-500' : 'text-green-500';
});
</script>
