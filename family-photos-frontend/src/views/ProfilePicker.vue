<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios';

const users = ref([]);

onMounted(async () => {
  try {
    // Because baseURL is .../v1/family-photos, this calls .../v1/family-photos/users
    const response = await api.get('/users');
    users.value = response.data;
  } catch (error) {
    console.error("Failed to fetch users", error);
  }
});

function getProfileImage(user) {
  // Use the full URL provided by the backend response
  return user.profile_photo_url;
}
</script>
