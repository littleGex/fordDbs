<template>
  <div class="w-full h-64">
    <Line v-if="chartData.labels.length > 0" :data="chartData" :options="chartOptions" />
    <div v-else class="h-full flex items-center justify-center text-gray-400">
      Not enough data for chart
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Line } from 'vue-chartjs';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const props = defineProps({
  history: {
    type: Array,
    required: true,
    default: () => []
  }
});

// Prepare data for the chart
const chartData = computed(() => {
  // We need at least 2 points to make a line
  if (props.history.length < 2) return { labels: [], datasets: [] };

  // Clone and reverse so chronological order is left-to-right
  const sortedHistory = [...props.history].reverse();

  return {
    labels: sortedHistory.map(entry => entry.date),
    datasets: [
      {
        label: 'Gas Usage (m³)',
        backgroundColor: '#3b82f6', // blue-500
        borderColor: '#3b82f6',
        data: sortedHistory.map(entry => entry.usage.gas),
        tension: 0.3 // Adds slight curve to the line
      },
      {
        label: 'Net Elect. (kWh)',
        backgroundColor: '#ef4444', // red-500
        borderColor: '#ef4444',
        data: sortedHistory.map(entry => entry.usage.net_elect),
        tension: 0.3
      }
    ]
  };
});

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'bottom' }
  },
  scales: {
    y: { beginAtZero: true }
  }
};
</script>
