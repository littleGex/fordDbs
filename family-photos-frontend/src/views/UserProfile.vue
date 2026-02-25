<template>
  <div class="user-container">
    <div v-if="currentMode === 'feed'" class="feed-view">
      <div class="feed-header">
        <h2 class="section-title">Family Moments</h2>
        <div class="filter-tabs">
          <button @click="toggleFilter(false)" :class="{ active: !showOnlyMyPhotos }" class="tab-btn">Everyone</button>
          <button @click="toggleFilter(true)" :class="{ active: showOnlyMyPhotos }" class="tab-btn">My Photos</button>
        </div>
      </div>

      <div class="photo-grid">
        <div v-for="photo in photos" :key="photo.id" class="photo-card-container">
          <img :src="photo.url" class="feed-img" loading="lazy" @load="recordView(photo.id)"/>

          <div class="photo-card-content">
            <p class="caption">
              <strong>{{ photo.uploader.display_name }}</strong> {{ photo.caption }}
            </p>

            <div class="interaction-bar">
              <button @click="handleLike(photo.id)" class="like-btn">
                ❤️ {{ photo.stats.likes }}
              </button>

              <span class="view-stat" title="Views">
                <svg class="icon-svg" viewBox="0 0 24 24">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                  <circle cx="12" cy="12" r="3"></circle>
                </svg>
                {{ photo.stats.views }}
              </span>
            </div>

            <div class="comments-preview">
              <div v-for="comment in photo.recent_comments" :key="comment.text" class="comment">
                <strong>{{ comment.username }}</strong> {{ comment.text }}
              </div>
            </div>

            <div class="comment-input-group">
              <input
                  v-model="commentTexts[photo.id]"
                  placeholder="Add a comment..."
                  @keyup.enter="handleComment(photo.id)"
              />
              <button class="post-comment-btn" @click="handleComment(photo.id)">Post</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="currentMode === 'profile'" class="profile-dashboard">
      <div class="profile-hero-card">
        <div class="profile-header">
          <img :src="auth.currentUser.profile_photo_url || '/avatars/default.png'" class="large-avatar-img"/>
          <div class="profile-info">
            <h1>{{ auth.currentUser.display_name }}</h1>
            <span class="role-pill">{{ auth.currentUser.role }}</span>
            <p class="bio-text">{{ auth.currentUser.bio || 'Sharing memories with the family.' }}</p>
          </div>
        </div>
        <div class="profile-actions">
          <button @click="currentMode = 'edit'" class="secondary-btn">Edit Profile</button>
          <button @click="auth.logout()" class="btn-switch">Logout / Switch</button>
        </div>
      </div>
    </div>

    <div v-else-if="currentMode === 'edit'" class="edit-view">
      <div class="edit-mode-card">
        <h3>Update Profile</h3>
        <div class="form-group">
          <label>Display Name</label>
          <input type="text" v-model="tempDisplayName"/>
        </div>
        <div class="form-group">
          <label>Profile Bio</label>
          <textarea v-model="tempBio" placeholder="Tell the family something about yourself..."></textarea>
        </div>
        <div class="form-group">
          <label>Change Photo</label>
          <input type="file" @change="onProfileFileSelected" accept="image/*"/>
        </div>
        <div class="actions">
          <button @click="saveProfile" class="save-btn" :disabled="uploading">
            {{ uploading ? 'Saving...' : 'Save Changes' }}
          </button>
          <button @click="currentMode = 'profile'" class="cancel-btn">Cancel</button>
        </div>
      </div>
    </div>

    <div v-if="showUploadModal" class="modal-overlay">
      <div class="modal-content">
        <h3>Post to Family Feed</h3>
        <input type="file" @change="onFeedFileSelected" accept="image/*"/>
        <textarea v-model="newCaption" placeholder="Write a caption (optional)..."></textarea>
        <div class="modal-actions">
          <button @click="handleUpload" :disabled="uploading" class="save-btn">Post Photo</button>
          <button @click="showUploadModal = false" class="cancel-btn">Cancel</button>
        </div>
      </div>
    </div>

    <div class="fab-container">
      <button class="fab-sub" @click="showUploadModal = true">📸</button>
      <button class="fab-main" @click="toggleView">
        {{ currentMode === 'feed' ? '👤' : '🖼️' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useAuthStore } from '../stores/auth';
import api from '../api/axios';

const auth = useAuthStore();
const currentMode = ref('feed');
const photos = ref([]);
const showOnlyMyPhotos = ref(false);
const uploading = ref(false);
const showUploadModal = ref(false);
const commentTexts = ref({});

// Form States
const newCaption = ref('');
const selectedFeedFile = ref(null);
const tempDisplayName = ref(auth.currentUser.display_name || '');
const tempBio = ref(auth.currentUser.bio || '');
const selectedProfileFile = ref(null);

const onFeedFileSelected = (e) => { selectedFeedFile.value = e.target.files[0]; };
const onProfileFileSelected = (e) => { selectedProfileFile.value = e.target.files[0]; };

const toggleView = () => {
  currentMode.value = currentMode.value === 'feed' ? 'profile' : 'feed';
};

const toggleFilter = (onlyMe) => {
  showOnlyMyPhotos.value = onlyMe;
  fetchPhotos();
};

const fetchPhotos = async () => {
  try {
    const params = showOnlyMyPhotos.value ? { user_id: auth.currentUser.id } : {};
    const res = await api.get('/feed', { params });
    photos.value = res.data;
  } catch (err) {
    console.error("Feed error:", err);
  }
};

const handleUpload = async () => {
  if (!selectedFeedFile.value) return;
  uploading.value = true;
  const formData = new FormData();
  formData.append('file', selectedFeedFile.value);
  formData.append('caption', newCaption.value || "");
  formData.append('uploader_id', auth.currentUser.id);
  try {
    await api.post('/upload', formData);
    showUploadModal.value = false;
    newCaption.value = '';
    fetchPhotos();
  } catch (err) { console.error(err); }
  finally { uploading.value = false; }
};

const handleLike = async (id) => {
  await api.post(`/${id}/like`, null, { params: { user_id: auth.currentUser.id } });
  fetchPhotos();
};

const handleComment = async (id) => {
  if (!commentTexts.value[id]) return;
  await api.post(`/${id}/comment`, null, { params: { user_id: auth.currentUser.id, text: commentTexts.value[id] } });
  commentTexts.value[id] = '';
  fetchPhotos();
};

const recordView = async (id) => {
  await api.post(`/${id}/view`, null, { params: { user_id: auth.currentUser.id } });
};

const saveProfile = async () => {
  uploading.value = true;
  const formData = new FormData();
  formData.append('user_id', auth.currentUser.id);
  formData.append('display_name', tempDisplayName.value);
  formData.append('bio', tempBio.value);
  if (selectedProfileFile.value) formData.append('file', selectedProfileFile.value);
  try {
    const res = await api.post('/profile/update', formData);
    auth.updateUser(res.data);
    currentMode.value = 'profile';
  } finally { uploading.value = false; }
};

onMounted(fetchPhotos);
</script>

<style scoped>
/* Scoped overrides if needed; otherwise relies on style.css */
.user-container { padding-top: 20px; }
</style>
