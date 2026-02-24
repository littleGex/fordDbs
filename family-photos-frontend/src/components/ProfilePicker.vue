<template>
  <div class="profile-picker">
    <h1>Who's watching?</h1>

    <div v-if="loading" class="loading">Loading profiles...</div>

    <div v-else class="user-grid">
      <div v-for="user in users" :key="user.id" class="profile-card" @click="selectUser(user)">
        <img :src="user.profile_photo_url || '/avatars/default.png'" class="avatar" />
        <h3>{{ user.display_name }}</h3>
      </div>

      <div class="profile-card add-tile" @click="showModal = true">
        <div class="avatar plus-avatar">
          <span>+</span>
        </div>
        <h3>Add Profile</h3>
      </div>
    </div>

    <div v-if="showModal" class="modal-overlay">
      <div class="modal-content">
        <h2>New Profile</h2>
        <input v-model="newUserName" placeholder="Enter name" @keyup.enter="createUser" />
        <div class="modal-btns">
          <button @click="showModal = false">Cancel</button>
          <button @click="createUser" :disabled="!newUserName">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios.js';
import { useAuthStore } from '../stores/auth.js';

const auth = useAuthStore();
const users = ref([]);
const loading = ref(true);
const showModal = ref(false);
const newUserName = ref('');

const fetchUsers = async () => {
  try {
    const response = await api.get('/users');
    users.value = response.data;
  } catch (error) {
    console.error("Failed to fetch users", error);
  } finally {
    loading.value = false;
  }
};

onMounted(fetchUsers);

const selectUser = (user) => auth.login(user);

const createUser = async () => {
  if (!newUserName.value) return;
  try {
    // Assuming your backend has a POST /users or similar endpoint
    // Adjust the URL/payload based on your actual database_manager_api
    await api.post('/users', {
      username: newUserName.value.toLowerCase().replace(/\s/g, ''),
      display_name: newUserName.value
    });
    newUserName.value = '';
    showModal.value = false;
    fetchUsers(); // Refresh the list
  } catch (error) {
    alert("Failed to create profile");
  }
};
</script>

<style scoped>
/* Add to your existing styles */
.plus-avatar {
  background: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 3rem;
  color: grey;
  transition: all 0.2s;
}

.add-tile:hover .plus-avatar {
  background: grey;
  color: white;
}

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.8);
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-content {
  background: #141414;
  padding: 30px;
  border-radius: 8px;
  text-align: center;
}

.modal-content input {
  padding: 10px;
  margin: 20px 0;
  width: 100%;
  background: #333;
  color: white;
  border: none;
}
</style>
