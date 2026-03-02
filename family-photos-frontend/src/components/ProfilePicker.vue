<template>
  <div class="profile-picker">
    <h1>Who's watching?</h1>

    <div v-if="loading" class="loading">Loading profiles...</div>

    <div v-else class="user-grid">
      <div v-for="user in users" :key="user.id" class="profile-card" @click="openLoginModal(user)">
        <img :src="user.profile_photo_url || '/avatars/default.png'" class="avatar" />
        <h3>{{ user.display_name }}</h3>
      </div>

      <div class="profile-card add-tile" @click="showCreateModal = true">
        <div class="avatar plus-avatar"><span>+</span></div>
        <h3>Add Profile</h3>
      </div>
    </div>

    <div v-if="showPassModal" class="modal-overlay">
      <div class="modal-content">
        <h2>{{ needsInitialSetup ? 'Set Your Password' : 'Enter Password' }}</h2>
        <p>Profile: {{ selectedUser?.display_name }}</p>
        <input
          v-model="passInput"
          type="password"
          :placeholder="needsInitialSetup ? 'Create a password' : 'Enter password'"
          @keyup.enter="submitAuth"
          autofocus
        />
        <div class="modal-btns">
          <button @click="closeModals">Cancel</button>
          <button @click="submitAuth">{{ needsInitialSetup ? 'Save & Login' : 'Unlock' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showCreateModal" class="modal-overlay">
      <div class="modal-content">
        <h2>New Profile</h2>
        <input v-model="newUserName" placeholder="Display Name" />
        <input v-model="newUserPassword" type="password" placeholder="Password" />
        <div class="modal-btns">
          <button @click="closeModals">Cancel</button>
          <button @click="createUser" :disabled="!newUserName || !newUserPassword">Create</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import api from '../api/axios.js';
import { useAuthStore } from '../stores/auth.js';

const auth = useAuthStore();
const router = useRouter();
const users = ref([]);
const loading = ref(true);

// Modal States
const showPassModal = ref(false);
const showCreateModal = ref(false);
const needsInitialSetup = ref(false);

// Form States
const selectedUser = ref(null);
const passInput = ref('');
const newUserName = ref('');
const newUserPassword = ref('');

const fetchUsers = async () => {
  try {
    const response = await api.get('/users');
    users.value = response.data;
  } catch (error) {
    console.error("Fetch error", error);
  } finally {
    loading.value = false;
  }
};

onMounted(fetchUsers);

const openLoginModal = (user) => {
  selectedUser.value = user;
  passInput.value = '';
  showPassModal.value = true;
  needsInitialSetup.value = false; // Reset setup flag
};

const closeModals = () => {
  showPassModal.value = false;
  showCreateModal.value = false;
  passInput.value = '';
};

const submitAuth = async () => {
  if (!passInput.value) {
    alert("Password is required");
    return;
  }

  try {
    let res;

    if (needsInitialSetup.value) {
      // FIX: Call the correct endpoint to SAVE the password first
      await api.post('/users/set-password', {
        user_id: selectedUser.value.id,
        password: passInput.value
      }, {
        // Manually restore content-type since it's deleted in axios.js
        headers: { 'Content-Type': 'application/json' }
      });

      // Now that it's saved, attempt a normal login
      res = await api.post('/login', {
        user_id: selectedUser.value.id,
        password: passInput.value
      }, {
        headers: { 'Content-Type': 'application/json' }
      });
    } else {
      // Normal login flow
      res = await api.post('/login', {
        user_id: selectedUser.value.id,
        password: passInput.value
      }, {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Handle the "needs setup" response from the backend
    if (res.data.status === 'needs_initial_password') {
      needsInitialSetup.value = true;
      return; // Stop here so the user can see the "Set Password" prompt
    }

    // Success: Store token and enter app
    localStorage.setItem('token', res.data.access_token);
    auth.login(selectedUser.value);
    router.push("/");
    showPassModal.value = false;

  } catch (err) {
    console.error("Auth error:", err.response?.data);
    alert(err.response?.data?.detail || "Authentication failed");
  }
};

const createUser = async () => {
  try {
    const generatedUsername = newUserName.value.toLowerCase().replace(/\s/g, '');
    await api.post('/users', {
      username: generatedUsername,
      display_name: newUserName.value,
      password: newUserPassword.value
    });
    newUserName.value = '';
    newUserPassword.value = '';
    showCreateModal.value = false;
    fetchUsers();
  } catch (error) {
    alert("Creation failed: " + (error.response?.data?.detail || "Check console"));
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
  font-size: 2.5rem; /* Better scale for the + icon */
  color: #808080;
}

.add-tile:hover .plus-avatar {
  background: #e5e5e5;
  color: #141414;
}

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 4000;
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
