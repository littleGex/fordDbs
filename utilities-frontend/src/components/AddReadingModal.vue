<template>
  <div class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
    <div class="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
      <div class="p-6 border-b border-gray-100 flex justify-between items-center">
        <h2 class="text-xl font-bold text-gray-900">New Meter Reading</h2>
        <button @click="$emit('close')" class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
      </div>

      <form @submit.prevent="submitReadings" class="p-6 space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Reading Date</label>
          <input
            v-model="formData.date"
            type="date"
            required
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
          />
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div v-for="util in utilities" :key="util.key">
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ util.label }}</label>
            <div class="relative">
              <input
                v-model.number="formData.readings[util.key]"
                type="number"
                step="0.01"
                placeholder="0.00"
                class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
              />
              <span class="absolute right-3 top-2 text-gray-400 text-xs">{{ util.unit }}</span>
            </div>
          </div>
        </div>

        <div class="pt-4 flex space-x-3">
          <button
            type="button"
            @click="$emit('close')"
            class="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition"
          >
            Cancel
          </button>
          <button
            type="submit"
            :disabled="isSubmitting"
            class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
          >
            {{ isSubmitting ? 'Saving...' : 'Save All' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue';
import axios from 'axios';

const emit = defineEmits(['close', 'refresh']);

const utilities = [
  { key: 'water', label: 'Water', unit: 'm³' },
  { key: 'gas', label: 'Gas', unit: 'm³' },
  { key: 'elect_u', label: 'Elect. Used', unit: 'kWh' },
  { key: 'elect_p', label: 'Elect. Prod', unit: 'kWh' }
];

const formData = reactive({
  date: new Date().toISOString().split('T')[0],
  readings: { water: null, gas: null, elect_u: null, elect_p: null }
});

const isSubmitting = ref(false);

const submitReadings = async () => {
  isSubmitting.value = true;
  const errors = [];

  // 1. Filter out empty values
  const activeReadings = Object.entries(formData.readings)
    .filter(([_, value]) => value !== null && value !== '');

  try {
    // 2. Loop through and send requests
    for (const [key, value] of activeReadings) {
      await axios.post(`${import.meta.env.VITE_API_BASE}/add-util`, null, {
        params: {
          util_date: formData.date,
          utility: key,
          util_reading: value
        }
      });
    }

    // 3. If all loops finish successfully
    emit('refresh');
    emit('close');

  } catch (error) {
    // This is where line 111 likely is—ensure the braces above are closed!
    alert("Error saving readings. Please try again.");
    console.error(error);
  } finally {
    isSubmitting.value = false;
  }
};
</script>
