<template>
  <div class="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
      <div class="p-6 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
        <h2 class="text-xl font-bold text-gray-900">
          {{ initialData ? 'Edit Readings' : 'New Meter Reading' }}
        </h2>
        <button @click="$emit('close')" class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
      </div>

      <form @submit.prevent="submitReadings" class="p-6 space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Reading Date</label>
          <input
            v-model="formData.date"
            type="date"
            required
            :disabled="!!initialData"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none disabled:bg-gray-100"
          />
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div v-for="util in utilities" :key="util.key">
            <label class="block text-sm font-medium text-gray-700 mb-1">{{ util.label }}</label>
            <input
              v-model.number="formData.readings[util.key]"
              type="number"
              step="0.01"
              :placeholder="util.unit"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>
        </div>

        <div class="pt-4 flex gap-3">
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
            class="flex-1 bg-blue-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50"
          >
            {{ isSubmitting ? 'Saving...' : 'Save All' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import axios from 'axios';

const props = defineProps(['initialData']);
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

onMounted(() => {
  if (props.initialData && props.initialData.readings) {
    formData.date = props.initialData.date;
    Object.keys(formData.readings).forEach(key => {
      // Use the readings object from the history entry
      const val = props.initialData.readings[key];
      formData.readings[key] = (val !== undefined) ? val : null;
    });
  }
});

const submitReadings = async () => {
  isSubmitting.value = true;
  try {
    const activeReadings = Object.entries(formData.readings)
      .filter(([_, value]) => value !== null && value !== '');

    for (const [key, value] of activeReadings) {
      await axios.post(`${import.meta.env.VITE_API_BASE}/add-util`, null, {
        params: { util_date: formData.date, utility: key, util_reading: value }
      });
    }
    emit('refresh');
    emit('close');
  } catch (err) {
    alert("Error saving data");
  } finally {
    isSubmitting.value = false;
  }
};
</script>
