<template>
  <div class="profile-picker">
    <h1>Who's watching?</h1>

    <div v-if="loading" class="loading">Loading profiles...</div>

    <div v-else class="user-grid">
      <div v-for="user in users" :key="user.id" class="profile-card" @click="openLoginModal(user)">
        <img :src="getAvatar(user)" class="avatar" />
        <h3>{{ user.display_name }}</h3>
      </div>

      <div class="profile-card add-tile" @click="showCreateModal = true">
        <div class="avatar plus-avatar"><span>+</span></div>
        <h3>Add Profile</h3>
      </div>
    </div>

    <div v-if="showPassModal" class="modal-overlay" @click.self="closeModals">
      <div class="modal-content">
        <h2>Enter Password</h2>
        <p>Profile: {{ selectedUser?.display_name }}</p>
        <input
          v-model="passInput"
          type="password"
          placeholder="Enter password"
          @keyup.enter="submitAuth"
          autofocus
          class="styled-input"
        />
        <div class="modal-btns">
          <button @click="closeModals" class="btn-secondary">Cancel</button>
          <button @click="submitAuth" class="btn-primary">Unlock</button>
        </div>
      </div>
    </div>

    <div v-if="showCreateModal" class="modal-overlay" @click.self="closeModals">
      <div v-if="requestSent" class="modal-content">
        <h2>Request Sent</h2>
        <p>Your profile is waiting for approval. You can log in once Dad has approved it.</p>
        <div class="modal-btns">
          <button @click="closeModals" class="btn-primary">OK</button>
        </div>
      </div>

      <div v-else class="modal-content">
        <h2>Add Profile</h2>

        <div class="avatar-setup">
          <img :src="newAvatarPreview" class="avatar large-preview" />

          <input
            type="file"
            ref="newProfileFileInput"
            @change="onNewProfileFileSelected"
            accept="image/*"
            class="hidden-file-input"
          />

          <button @click="$refs.newProfileFileInput.click()" class="btn-secondary mini-btn">
            Upload Photo
          </button>
        </div>

        <input
          v-model="newUserName"
          type="text"
          placeholder="Display Name"
          class="styled-input"
        />
        <input
          v-model="newUserPassword"
          type="password"
          placeholder="Password"
          class="styled-input"
        />
        <input
          v-model.number="newUserBirthYear"
          type="number"
          inputmode="numeric"
          placeholder="Year you were born"
          @keyup.enter="createUser"
          class="styled-input"
        />

        <div class="modal-btns">
          <button @click="closeModals" class="btn-secondary">Cancel</button>
          <button @click="createUser" class="btn-primary" :disabled="!newUserName || !newUserPassword || !newUserBirthYear">Send Request</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import api from '../api/axios.js';
import { useAuthStore } from '../stores/auth.js';
import { getAvatar } from '../utils/avatar.js';

const auth = useAuthStore();
const router = useRouter();
const users = ref([]);
const loading = ref(true);

// Modal States
const showPassModal = ref(false);
const showCreateModal = ref(false);

// Form States
const selectedUser = ref(null);
const passInput = ref('');
const newUserName = ref('');
const newUserPassword = ref('');
const newUserBirthYear = ref(null);
const requestSent = ref(false);
const newProfileFile = ref(null);
const uploadedPreviewUrl = ref(null);

const fetchUsers = async () => {
  try {
    const response = await api.get('/login-options');
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
};

const closeModals = () => {
  showPassModal.value = false;
  showCreateModal.value = false;
  passInput.value = '';
  // Reset create form if closed
  newUserName.value = '';
  newUserPassword.value = '';
  newUserBirthYear.value = null;
  requestSent.value = false;
  newProfileFile.value = null;
  uploadedPreviewUrl.value = null;
};

const submitAuth = async () => {
  if (!passInput.value) {
    alert("Password is required");
    return;
  }

  try {
    const res = await api.post('/login', {
      user_id: selectedUser.value.id,
      password: passInput.value
    }, {
      headers: { 'Content-Type': 'application/json' }
    });

    localStorage.setItem('token', res.data.access_token);
    // The picker only knows a name and avatar; the full profile (role,
    // bio) comes back with the token
    auth.login({ ...selectedUser.value, ...res.data.user });
    router.push("/home");
    showPassModal.value = false;

  } catch (err) {
    console.error("Auth error:", err.response?.data);
    alert(err.response?.data?.detail || "Authentication failed");
  }
};

const newAvatarPreview = computed(() => {
  if (uploadedPreviewUrl.value) return uploadedPreviewUrl.value;

  if (newUserName.value) {
    return `https://ui-avatars.com/api/?name=${encodeURIComponent(newUserName.value)}&background=333333&color=fff&size=150`;
  }

  return 'https://ui-avatars.com/api/?name=New+User&background=141414&color=333&size=150';
});

const onNewProfileFileSelected = (e) => {
  const file = e.target.files[0];
  if (!file) return;
  newProfileFile.value = file;
  uploadedPreviewUrl.value = URL.createObjectURL(file);
};

const createUser = async () => {
  try {
    const generatedUsername = newUserName.value.toLowerCase().replace(/\s/g, '');

    const formData = new FormData();
    formData.append('username', generatedUsername);
    formData.append('display_name', newUserName.value);
    formData.append('password', newUserPassword.value);
    // Only used to suggest child or adult; the server doesn't keep it
    formData.append('birth_year', newUserBirthYear.value);

    if (newProfileFile.value) {
      formData.append('file', newProfileFile.value);
    }

    await api.post('/users', formData);

    // The new profile stays hidden until the admin approves it
    requestSent.value = true;
  } catch (error) {
    alert("Creation failed: " + (error.response?.data?.detail || "Check console"));
  }
};
</script>

<style scoped>
/* Profile Grid Styles */
.plus-avatar {
  background: #333;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.5rem;
  color: #808080;
}

.add-tile:hover .plus-avatar {
  background: #e5e5e5;
  color: #141414;
}

/* Modal Core Styles */
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
  width: 90%;
  max-width: 400px; /* Keep modal from getting too wide on desktop */
}

/* Avatar Upload Styles */
.avatar-setup {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
  margin-bottom: 20px;
}

.large-preview {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  border: 3px solid #333;
  object-fit: cover;
}

.hidden-file-input {
  display: none;
}

/* Form Input Styles */
.styled-input {
  width: 100%;
  padding: 12px;
  background: #2b2b2b;
  border: 1px solid #444;
  border-radius: 6px;
  color: white;
  margin-bottom: 15px;
  box-sizing: border-box; /* Ensures padding doesn't push width over 100% */
}

.styled-input:focus {
  outline: none;
  border-color: #e50914; /* Netflix red focus ring */
}

.mini-btn {
  padding: 6px 12px;
  font-size: 0.85rem;
}

/* Modal Buttons Flexbox */
.modal-btns {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}

.modal-btns button {
  flex: 1; /* Makes buttons equal width */
}
</style>
