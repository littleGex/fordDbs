<template>
  <div class="w-full h-64">
    <Line v-if="chartData.labels.length > 0" :data="chartData" :options="chartOptions"/>
    <div v-else class="h-full flex items-center justify-center text-gray-400">
      Not enough data for chart
    </div>
  </div>
</template>

<script setup>
import {computed} from 'vue';
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
import {Line} from 'vue-chartjs';

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
  if (props.history.length < 2) return {labels: [], datasets: []};
  const sorted = [...props.history].reverse();

  return {
    labels: sorted.map(e => e.date),
    datasets: [
      {label: 'Water (m³)', borderColor: '#0ea5e9', data: sorted.map(e => e.usage.water), tension: 0.3},
      {label: 'Gas (m³)', borderColor: '#f97316', data: sorted.map(e => e.usage.gas), tension: 0.3},
      {label: 'Elect Used (kWh)', borderColor: '#ef4444', data: sorted.map(e => e.usage.elect_u), tension: 0.3},
      {label: 'Elect Produced (kWh)', borderColor: '#facc15', data: sorted.map(e => e.usage.elect_p), tension: 0.3}
    ]
  };
});

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {position: 'bottom'}
  },
  scales: {
    y: {beginAtZero: true}
  }
};
</script>
