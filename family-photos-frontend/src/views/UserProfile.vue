<template>
  <div :class="['user-container', currentTheme]">
    <div v-if="currentMode === 'feed'" class="feed-view">
      <div class="feed-header">
        <div class="seasonal-overlay">
          <div v-for="(style, index) in particles" :key="index" class="particle" :style="style"></div>
        </div>

        <h2 class="section-title">Family Moments</h2>

        <div class="filter-tabs">
          <button @click="toggleFilter(false)" :class="{ active: !showOnlyMyPhotos }" class="tab-btn">Everyone</button>
          <button @click="toggleFilter(true)" :class="{ active: showOnlyMyPhotos }" class="tab-btn">My Photos</button>
        </div>
      </div>

      <div class="photo-grid">
        <div v-for="photo in photos" :key="photo.id" class="photo-card">
          <img :src="photo.url" loading="lazy" @load="recordView(photo.id)"/>

          <div class="photo-content">
            <p class="caption">
              <strong>{{ photo.uploader.display_name }}</strong> {{ photo.caption }}
            </p>

            <div class="interaction-bar">
              <button @click="handleLike(photo.id)" class="like-btn">
                ❤️ {{ photo.stats.likes }}
              </button>
              <span class="view-count">👥 {{ photo.stats.views }}</span>
            </div>

            <div class="comments-preview">
              <div v-for="comment in photo.recent_comments" :key="comment.text" class="comment">
                <strong>{{ comment.username }}</strong> {{ comment.text }}
              </div>
            </div>

            <div class="comment-input-area">
              <input v-model="commentTexts[photo.id]" placeholder="Add a comment..."
                     @keyup.enter="handleComment(photo.id)"/>
              <button @click="handleComment(photo.id)">Post</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="currentMode === 'profile'" class="bio-view">
      <div class="bio-card">
        <img :src="auth.currentUser.profile_photo_url || '/avatars/default.png'" class="large-avatar"/>
        <h1>{{ auth.currentUser.display_name }}</h1>
        <p class="bio-text">{{ auth.currentUser.bio || 'Sharing memories with the family.' }}</p>
        <div style="margin-top: 20px; display: flex; gap: 10px; justify-content: center;">
          <button @click="currentMode = 'edit'" class="like-btn">Edit Profile</button>
          <button @click="auth.logout()" class="like-btn">Switch Profile</button>
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
        <div style="margin-top: 20px; display: flex; gap: 10px; justify-content: center;">
          <button @click="saveProfile" class="like-btn" :disabled="uploading">
            {{ uploading ? 'Saving...' : 'Save Changes' }}
          </button>
          <button @click="currentMode = 'profile'" class="like-btn">Cancel</button>
        </div>
      </div>
    </div>

    <div v-if="showUploadModal" class="modal-overlay">
      <div class="modal-content">
        <h3>Post to Family Feed</h3>
        <input type="file" @change="onFeedFileSelected" accept="image/*" style="margin: 20px 0; color: white;"/>
        <textarea v-model="newCaption" placeholder="Write a caption (optional)..."
                  style="width: 100%; background: #2b2b2b; color: white; border: 1px solid #444; padding: 10px; margin-bottom: 20px;"></textarea>
        <div style="display: flex; gap: 10px; justify-content: center;">
          <button @click="handleUpload" :disabled="uploading" class="like-btn">Post Photo</button>
          <button @click="showUploadModal = false" class="like-btn">Cancel</button>
        </div>
      </div>
    </div>

    <div class="fab-container">
      <button class="fab-sub" @click="showUploadModal = true" title="Upload Photo">📸</button>

      <button class="fab-main" @click="currentMode = currentMode === 'feed' ? 'profile' : 'feed'">
        {{ currentMode === 'feed' ? '👤' : '🖼️' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import {ref, onMounted, computed} from 'vue';
import {useAuthStore} from '../stores/auth';
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
const particles = ref([]);

const onFeedFileSelected = (e) => {
  selectedFeedFile.value = e.target.files[0];
};
const onProfileFileSelected = (e) => {
  selectedProfileFile.value = e.target.files[0];
};

const toggleView = () => {
  currentMode.value = currentMode.value === 'feed' ? 'profile' : 'feed';
};

const toggleFilter = (onlyMe) => {
  showOnlyMyPhotos.value = onlyMe;
  fetchPhotos();
};

const currentTheme = computed(() => {
  const month = new Date().getMonth();
  if (month >= 2 && month <= 4) return 'theme-spring';
  if (month >= 5 && month <= 7) return 'theme-summer';
  if (month >= 8 && month <= 10) return 'theme-halloween';
  return 'theme-winter';
});

const fetchPhotos = async () => {
  try {
    const params = showOnlyMyPhotos.value ? {user_id: auth.currentUser.id} : {};
    const res = await api.get('/feed', {params});
    photos.value = res.data;
  } catch (err) {
    console.error("Feed error:", err);
  }
};

const handleUpload = async () => {
  if (!selectedFeedFile.value) {
    alert("Please select a photo first!");
    return;
  }

  uploading.value = true;
  const formData = new FormData();
  formData.append('file', selectedFeedFile.value);
  formData.append('caption', newCaption.value || "");
  formData.append('uploader_id', auth.currentUser.id);

  try {
    await api.post('/upload', formData);

    // Reset state only on success
    showUploadModal.value = false;
    newCaption.value = '';
    selectedFeedFile.value = null;
    fetchPhotos();
  } catch (err) {
    console.error("Upload failed:", err);
    alert("Upload failed. Please try again.");
  } finally {
    uploading.value = false;
  }
};

const handleLike = async (id) => {
  await api.post(`/${id}/like`);
  fetchPhotos();
};

const handleComment = async (id) => {
  if (!commentTexts.value[id]) return;
  // Use URLSearchParams for Form data if backend expects it, otherwise a simple object
  const formData = new FormData();
  formData.append('text', commentTexts.value[id]);

  await api.post(`/${id}/comment`, formData);
  commentTexts.value[id] = '';
  fetchPhotos();
};

const handleDelete = async (photoId) => {
  if (!confirm("Are you sure you want to delete this memory?")) return;

  try {
    // No need to pass user_id; the backend gets it from the header
    await api.delete(`/${photoId}`);

    // Refresh the feed to show the photo is gone
    fetchPhotos();
  } catch (err) {
    const msg = err.response?.data?.detail || "Delete failed";
    alert(msg);
  }
};

const recordView = async (id) => {
  await api.post(`/${id}/view`);
};

const saveProfile = async () => {
  uploading.value = true;
  const formData = new FormData();

  formData.append('display_name', tempDisplayName.value);
  formData.append('bio', tempBio.value);

  if (selectedProfileFile.value) {
    formData.append('file', selectedProfileFile.value);
  }

  try {
    const res = await api.post('/profile/update', formData);
    auth.updateUser(res.data);
    currentMode.value = 'profile';
  } catch (err) {
    console.error("Profile update failed:", err);
  } finally {
    uploading.value = false;
  }
};

onMounted(() => {
  fetchPhotos();
  // Icons now fall only within the header width
  particles.value = Array.from({length: 15}).map(() => ({
    left: `${Math.random() * 100}%`,
    animationDuration: `${Math.random() * 3 + 3}s`,
    animationDelay: `${Math.random() * 5}s`
  }));
});
</script>

<style scoped>
/* Scoped overrides if needed; otherwise relies on style.css */
.user-container {
  padding-top: 20px;
}
</style>
