<template>
  <div class="min-h-screen bg-gray-50 p-4 md:p-8">
    <div class="max-w-7xl mx-auto">
      <header class="flex justify-between items-center mb-8">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Utility Dashboard</h1>
          <p class="text-gray-500">Tracking usage, production, and trends</p>
        </div>
        <button
          @click="showModal = true"
          class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition"
        >
          + Add Reading
        </button>
      </header>

      <div v-if="!isLoading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <UtilityCard title="Water" :value="data.latest.readings?.water" unit="m³" :usage="data.latest.usage?.water" />
        <UtilityCard title="Gas" :value="data.latest.readings?.gas" unit="m³" :usage="data.latest.usage?.gas" />
        <UtilityCard title="Elect. Used" :value="data.latest.readings?.elect_u" unit="kWh" :usage="data.latest.usage?.elect_u" />
        <UtilityCard title="Net Electricity" :value="data.latest.usage?.net_elect" unit="kWh" :usage="null" />
      </div>

      <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <table class="w-full text-left">
          <thead class="bg-gray-50 border-b border-gray-100">
            <tr>
              <th class="px-6 py-4 text-sm font-semibold text-gray-600">Date</th>
              <th class="px-6 py-4 text-sm font-semibold text-gray-600 text-right">Water (Δ)</th>
              <th class="px-6 py-4 text-sm font-semibold text-gray-600 text-right">Gas (Δ)</th>
              <th class="px-6 py-4 text-sm font-semibold text-gray-600 text-right">Net Elect.</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-if="isLoading">
              <td colspan="4" class="px-6 py-10 text-center text-gray-400">Loading data...</td>
            </tr>

            <tr v-else-if="data.history.length === 0">
              <td colspan="4" class="px-6 py-10 text-center text-gray-400 italic">
                No readings found. Click "+ Add Reading" to get started.
              </td>
            </tr>

            <tr v-for="entry in data.history" :key="entry.date"
                :class="{'bg-blue-50/50': entry.is_february}">
              <td class="px-6 py-4">
                <span class="font-medium text-gray-900">{{ entry.date }}</span>
                <span v-if="entry.is_february" class="ml-2 text-[10px] bg-blue-100 text-blue-700 px-2 py-0.5 rounded uppercase font-bold">Official</span>
              </td>
              <td class="px-6 py-4 text-right">{{ entry.usage.water }} m³</td>
              <td class="px-6 py-4 text-right">{{ entry.usage.gas }} m³</td>
              <td class="px-6 py-4 text-right font-semibold" :class="entry.usage.net_elect > 0 ? 'text-red-600' : 'text-green-600'">
                {{ entry.usage.net_elect }} kWh
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <AddReadingModal
      v-if="showModal"
      @close="showModal = false"
      @refresh="fetchData"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import axios from 'axios';
import UtilityCard from '../components/UtilityCard.vue';
import AddReadingModal from "../components/AddReadingModal.vue";

const showModal = ref(false);
const isLoading = ref(true);
const data = ref({ latest: { readings: {}, usage: {} }, history: [] });

const fetchData = async () => {
  isLoading.value = true;
  try {
    const response = await axios.get(`${import.meta.env.VITE_API_BASE}/utilities/dashboard`);
    data.value = response.data;
  } catch (error) {
    console.error("Failed to fetch dashboard data:", error);
  } finally {
    isLoading.value = false;
  }
};

onMounted(fetchData);
</script>
