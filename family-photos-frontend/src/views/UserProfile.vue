<template>
  <div class="user-profile-container">
    <div v-if="auth.currentUser" class="profile-card-edit">
      <h2>Edit Profile</h2>

      <div class="profile-header">
        <img :src="getCleanImageUrl(auth.currentUser)" class="avatar-large" />
        <div class="header-text">
           <p class="display-name">{{ auth.currentUser.display_name }}</p>
           <p class="role-tag">{{ auth.currentUser.role }}</p>
        </div>
      </div>

      <div class="form-group">
        <label>Bio</label>
        <textarea
          v-model="bio"
          placeholder="Write something about yourself..."
          class="bio-input"
        ></textarea>
      </div>

      <div class="form-group">
        <label>Update Photo</label>
        <input type="file" @change="onFileSelected" accept="image/*" />
      </div>

      <button @click="handleUpdate" :disabled="isSaving" class="save-btn">
        {{ isSaving ? 'Saving...' : 'Save Changes' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import api from '../api/axios';
import { useAuthStore } from '../stores/auth';

const auth = useAuthStore();
const bio = ref(auth.currentUser?.bio || '');
const selectedFile = ref(null);
const isSaving = ref(false);

const onFileSelected = (e) => {
  selectedFile.value = e.target.files[0];
};

const handleUpdate = async () => {
  isSaving.value = true;
  const formData = new FormData();
  formData.append('user_id', auth.currentUser.id);
  formData.append('bio', bio.value);

  if (selectedFile.value) {
    formData.append('file', selectedFile.value);
  }

  try {
    const response = await api.post('/profile/update', formData);
    auth.login(response.data); // Refresh local data
    alert("Profile saved!");
  } catch (err) {
    console.error(err);
    alert("Failed to update profile. Check if the backend is running.");
  } finally {
    isSaving.value = false;
  }
};

// Same helper function to keep URLs clean
function getCleanImageUrl(user) {
  if (!user.profile_photo_url) return '/avatars/default.png';
  const match = user.profile_photo_url.match(/\/([^/?#]+)[^/]*$/);
  return `http://ford-home-pi.local:9000/family-photos/avatars/${match ? match[1] : 'default.png'}`;
}
</script>
