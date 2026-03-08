<template>
  <div class="min-h-screen bg-gray-50 p-4 md:p-8">
    <div class="max-w-7xl mx-auto space-y-6">

      <header
          class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
        <div>
          <h1 class="text-3xl font-extrabold text-gray-900 tracking-tight">Utility Dashboard</h1>
          <p class="text-sm text-gray-500 mt-1">Real-time usage and historical trends.</p>
        </div>
        <button @click="openAddModal"
                class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl font-semibold shadow-sm transition-all">
          + Add Reading
        </button>
      </header>

      <div v-if="isLoading" class="flex justify-center py-20">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>

      <template v-else>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <UtilityCard title="Water" :value="data.latest.readings?.water" unit="m³" :usage="data.latest.usage?.water"/>
          <UtilityCard title="Gas" :value="data.latest.readings?.gas" unit="m³" :usage="data.latest.usage?.gas"/>
          <UtilityCard title="Elect. Used" :value="data.latest.readings?.elect_u" unit="kWh"
                       :usage="data.latest.usage?.elect_u"/>
          <UtilityCard
              title="Elect. Prod"
              :value="data.latest.readings?.elect_p"
              unit="kWh"
              :usage="data.latest.usage?.elect_p"
              :is-inverse="true"
              :is-reset="data.latest.resets?.elect_p"
          />
        </div>

        <div class="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <h2 class="text-lg font-bold text-gray-900 mb-4">All Utilities Trend</h2>
          <UsageChart :history="data.history"/>
        </div>

        <div class="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <table class="w-full text-left border-collapse">
            <thead class="bg-gray-50/50">
            <tr>
              <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Date</th>
              <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase text-right">Water (Δ)</th>
              <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase text-right">Gas (Δ)</th>
              <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase text-right">Elect. Used (Δ)</th>
              <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase text-right">Elect. Prod (Δ)</th>
              <th class="px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Actions</th>
            </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
            <tr v-for="entry in data.history" :key="entry.date" class="hover:bg-gray-50 transition-colors">
              <td class="px-6 py-4 font-medium">{{ entry.date }}</td>
              <td class="px-6 py-4 text-right">{{ entry.usage.water }} m³</td>
              <td class="px-6 py-4 text-right">{{ entry.usage.gas }} m³</td>

              <td class="px-6 py-4 text-right font-medium text-red-600">
                {{ entry.usage.elect_u }} kWh
              </td>

              <td class="px-6 py-4 text-right font-medium text-green-600">
                {{ entry.usage.elect_p }} kWh
              </td>

              <td class="px-6 py-4">
                <button @click="openEditModal(entry)" class="text-blue-600 hover:underline">Edit</button>
              </td>
            </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <AddReadingModal
        v-if="showModal"
        :initial-data="selectedEntry"
        @close="closeModal"
        @refresh="fetchData"
    />
  </div>
</template>

<script setup>
import {ref, onMounted} from 'vue';
import axios from 'axios';
import UtilityCard from '../components/UtilityCard.vue';
import UsageChart from '../components/UsageChart.vue';
import AddReadingModal from "../components/AddReadingModal.vue";

const showModal = ref(false);
const selectedEntry = ref(null);
const isLoading = ref(true);

const data = ref({latest: {readings: {}, usage: {}}, history: []});

const openAddModal = () => {
  selectedEntry.value = null; // Ensure it's empty for a new entry
  showModal.value = true;
};

const openEditModal = (entry) => {
  // We pass the whole history entry which contains the readings for that date
  selectedEntry.value = entry;
  showModal.value = true;
};

const closeModal = () => {
  showModal.value = false;
  selectedEntry.value = null;
};

const fetchData = async () => {
  isLoading.value = true;
  try {
    const res = await axios.get(`${import.meta.env.VITE_API_BASE}/dashboard`);
    data.value = res.data;
  } catch (err) {
    console.error(err);
  } finally {
    isLoading.value = false;
  }
};

const checkIfReset = (key) => {
  if (data.value.history.length < 2) return false;
  const current = data.value.history[0].readings[key];
  const previous = data.value.history[1].readings[key];
  // If current reading is lower than previous, a reset (new meter) happened
  return current < previous;
};

onMounted(fetchData);
</script>
