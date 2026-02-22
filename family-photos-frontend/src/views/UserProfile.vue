<template>
  <div class="user-profile-container">
    <div class="profile-card-edit">
      <h2>Edit Profile: {{ auth.currentUser.display_name }}</h2>

      <div class="current-avatar-section">
        <img :src="auth.currentUser.profile_photo_url" class="avatar-large" />
        <p>Current Profile Photo</p>
      </div>

      <div class="form-group">
        <label>Update Bio</label>
        <textarea
          v-model="bio"
          placeholder="Tell us something about yourself..."
          rows="4"
        ></textarea>
      </div>

      <div class="form-group">
        <label>Change Profile Photo</label>
        <input type="file" @change="onFileSelected" accept="image/*" class="file-input" />
      </div>

      <div class="actions">
        <button @click="saveProfile" :disabled="loading" class="save-btn">
          {{ loading ? 'Saving...' : 'Save Changes' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const selectedFile = ref(null);
const bio = ref(auth.currentUser.bio || ''); // Initialize with current bio
const loading = ref(false);

const onFileSelected = (event) => {
  selectedFile.value = event.target.files[0];
};

const saveProfile = async () => {
  loading.value = true;
  const formData = new FormData();
  formData.append('user_id', auth.currentUser.id);
  formData.append('bio', bio.value); // Send the bio text

  if (selectedFile.value) {
    formData.append('file', selectedFile.value);
  }

  try {
    const response = await api.post('/profile/update', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });

    // Update the local auth store so the UI reflects changes immediately
    auth.login(response.data);
    alert("Profile updated successfully!");
  } catch (error) {
    console.error("Update failed", error);
    alert("Error updating profile.");
  } finally {
    loading.value = false;
  }
};
</script>
