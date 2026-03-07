<template>
  <div class="min-h-screen bg-gray-50 p-4 md:p-8">
    <div class="max-w-7xl mx-auto space-y-6">

      <header class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <div>
          <h1 class="text-3xl font-extrabold text-gray-900 tracking-tight">Utility Dashboard</h1>
          <p class="text-sm text-gray-500 mt-1">Track your home's usage, production, and trends.</p>
        </div>
        <button
            @click="showModal = true"
            class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl font-semibold shadow-sm hover:shadow transition-all flex items-center gap-2"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd"/>
          </svg>
          Add Reading
        </button>
      </header>

      <div v-if="isLoading" class="flex justify-center items-center py-20">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>

      <template v-else>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <UtilityCard title="Water" :value="data.latest.readings?.water" unit="m³" :usage="data.latest.usage?.water"/>
          <UtilityCard title="Gas" :value="data.latest.readings?.gas" unit="m³" :usage="data.latest.usage?.gas"/>
          <UtilityCard title="Elect. Used" :value="data.latest.readings?.elect_u" unit="kWh" :usage="data.latest.usage?.elect_u"/>
          <UtilityCard title="Net Electricity" :value="data.latest.usage?.net_elect" unit="kWh" :usage="null"/>
        </div>

        <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <h2 class="text-lg font-bold text-gray-900 mb-4">Usage Trends</h2>
          <UsageChart :history="data.history" />
        </div>

        <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <div class="p-6 border-b border-gray-100">
            <h2 class="text-lg font-bold text-gray-900">Previous Records</h2>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-left border-collapse">
              <thead class="bg-gray-50/50">
              <tr>
                <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
                <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">Water (Δ)</th>
                <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">Gas (Δ)</th>
                <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">Net Elect.</th>
                <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">Actions</th>
              </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
              <tr v-if="data.history.length === 0">
                <td colspan="5" class="px-6 py-12 text-center text-gray-400 italic">
                  No readings found. Click "+ Add Reading" to get started.
                </td>
              </tr>

              <tr v-for="entry in data.history" :key="entry.date"
                  class="hover:bg-gray-50 transition-colors"
                  :class="{'bg-blue-50/30': entry.is_february}">
                <td class="px-6 py-4 whitespace-nowrap font-medium text-gray-900">
                  {{ entry.date }}
                  <span v-if="entry.is_february" class="ml-2 text-[10px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full uppercase font-bold tracking-wide">Official</span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-right text-gray-600">{{ entry.usage.water }} m³</td>
                <td class="px-6 py-4 whitespace-nowrap text-right text-gray-600">{{ entry.usage.gas }} m³</td>
                <td class="px-6 py-4 whitespace-nowrap text-right">
                    <span class="inline-flex items-center px-2.5 py-1 rounded-full text-sm font-medium"
                          :class="entry.usage.net_elect > 0 ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'">
                      {{ entry.usage.net_elect }} kWh
                    </span>
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-right">
                  <button
                      @click="openEditModal(entry)"
                      class="text-blue-600 hover:text-blue-800 text-sm font-medium transition-colors"
                  >
                    Edit
                  </button>
                </td>
              </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>

    <AddReadingModal
        v-if="showModal"
        @close="showModal = false"
        @refresh="fetchData"
    />

    <AddReadingModal
        v-if="showEditModal"
        :initial-data="selectedEntry"
        @close="showEditModal = false"
        @refresh="fetchData"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import axios from 'axios';
import UtilityCard from '../components/UtilityCard.vue';
import UsageChart from '../components/UsageChart.vue';
import AddReadingModal from "../components/AddReadingModal.vue";

const showModal = ref(false);
const showEditModal = ref(false);
const selectedEntry = ref(null);
const isLoading = ref(true);

const data = ref({
  latest: {
    readings: { water: 0, gas: 0, elect_u: 0 },
    usage: { water: 0, gas: 0, elect_u: 0, net_elect: 0 }
  },
  history: []
});

const openEditModal = (entry) => {
  selectedEntry.value = entry;
  showEditModal.value = true;
};

const fetchData = async () => {
  isLoading.value = true;
  try {
    const response = await axios.get(`${import.meta.env.VITE_API_BASE}/dashboard`);
    if (response.data && response.data.latest) {
      data.value = response.data;
    }
  } catch (error) {
    console.error("Failed to fetch dashboard data:", error);
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchData);
</script>
