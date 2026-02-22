<template>
  <div class="user-profile">
    <h2>Edit Profile</h2>
    <div class="upload-container">
      <input type="file" @change="onFileSelected" accept="image/*" />
      <button @click="saveProfile">Save New Profile Photo</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import api from '../api/axios';
import { useAuthStore } from '../stores/auth'; // To know who is logged in

const auth = useAuthStore();
const selectedFile = ref(null);

const onFileSelected = (event) => {
  selectedFile.value = event.target.files[0];
};

const saveProfile = async () => {
  const formData = new FormData();
  formData.append('user_id', auth.currentUser.id);
  if (selectedFile.value) {
    formData.append('file', selectedFile.value); // The "Photo Picked" part
  }

  // Hits your existing endpoint in family_photos.py
  await api.post('/profile/update', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
};
</script>
