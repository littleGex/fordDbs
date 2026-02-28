<template>
  <div class="user-container">
    <div v-if="currentMode === 'feed'" class="feed-view">

      <div class="feed-header">
        <h2 class="section-title">Family Moments</h2>
        <div class="segmented-control">
          <button
            @click="currentView = 'feed'; selectedAlbum = null"
            :class="{ active: currentView === 'feed' }"
          >Timeline</button>
          <button
            @click="currentView = 'albums'; selectedAlbum = null"
            :class="{ active: currentView === 'albums' }"
          >Albums</button>
        </div>
      </div>

      <div v-if="historicalPhotos.length > 0 && currentView === 'feed'" class="on-this-day-container">
        <h3 class="historical-title">
          <span class="icon">📅</span> On This Day...
        </h3>
        <div class="historical-scroll">
          <div v-for="photo in historicalPhotos" :key="photo.id" class="historical-card">
            <img :src="photo.url" loading="lazy" />
            <div class="historical-label">{{ getYearAgoText(photo.timestamp) }}</div>
          </div>
        </div>
      </div>

      <div v-if="currentView === 'feed'" class="photo-grid">
        <div class="filter-container" style="grid-column: 1/-1; margin-bottom: 10px;">
          <div class="segmented-control mini">
            <button @click="toggleFilter(false)" :class="{ active: !showOnlyMyPhotos }">Family</button>
            <button @click="toggleFilter(true)" :class="{ active: showOnlyMyPhotos }">Mine</button>
          </div>
        </div>

        <div v-for="photo in photos" :key="photo.id" class="photo-card">
          <img :src="photo.url" loading="lazy" @load="recordView(photo.id)"/>
          <div class="photo-content">
            <p class="caption">
              <strong>{{ photo.uploader.display_name }}</strong> {{ photo.caption }}
            </p>
            <div class="interaction-bar">
              <button @click="handleLike(photo.id)" class="like-btn">❤️ {{ photo.stats.likes }}</button>
              <span class="view-count">👥 {{ photo.stats.views }}</span>
            </div>
            <div class="comments-preview">
              <div v-for="comment in photo.recent_comments" :key="comment.text" class="comment">
                <strong>{{ comment.username }}</strong> {{ comment.text }}
              </div>
            </div>
            <div class="comment-input-area">
              <input v-model="commentTexts[photo.id]" placeholder="Add a comment..." @keyup.enter="handleComment(photo.id)"/>
              <button @click="handleComment(photo.id)">Post</button>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="currentView === 'albums' && !selectedAlbum" class="photo-grid">
        <div class="photo-card album-placeholder" @click="handleCreateAlbum">
           <div class="placeholder-content">
             <span class="plus-icon">+</span>
             <p>New Album</p>
           </div>
        </div>

        <div v-for="album in albums" :key="album.id" class="photo-card album-card" @click="openAlbum(album)">
          <img :src="album.cover_url || '/placeholder-album.png'" class="album-cover"/>
          <div class="photo-content album-info">
            <h3>{{ album.title }}</h3>
            <p>{{ album.photo_count }} Photos</p>
          </div>
        </div>
      </div>

      <div v-else-if="selectedAlbum" class="album-detail-view">
        <div class="feed-header detail-header">
          <button @click="selectedAlbum = null" class="back-btn">← Back to Albums</button>
          <h2 class="section-title">{{ selectedAlbum.title }}</h2>
        </div>
        <div class="photo-grid">
          <div v-for="photo in albumPhotos" :key="photo.id" class="photo-card">
            <img :src="photo.url" loading="lazy"/>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="currentMode === 'profile'" class="bio-view">
      <div class="bio-card">
        <img :src="auth.currentUser.profile_photo_url || '/avatars/default.png'" class="large-avatar"/>
        <h1>{{ auth.currentUser.display_name }}</h1>
        <p class="bio-text">{{ auth.currentUser.bio || 'Sharing memories with the family.' }}</p>
        <div class="profile-actions">
          <button @click="currentMode = 'edit'" class="like-btn">Edit Profile</button>
          <button @click="auth.logout()" class="like-btn">Logout</button>
        </div>
      </div>
    </div>

    <div v-else-if="currentMode === 'edit'" class="edit-view">
      <div class="edit-mode-card">
        <h3>Update Profile</h3>
        <div class="form-group"><label>Display Name</label><input type="text" v-model="tempDisplayName"/></div>
        <div class="form-group"><label>Profile Bio</label><textarea v-model="tempBio"></textarea></div>
        <div class="form-group"><label>Change Photo</label><input type="file" @change="onProfileFileSelected" accept="image/*"/></div>
        <div class="profile-actions">
          <button @click="saveProfile" class="like-btn" :disabled="uploading">{{ uploading ? 'Saving...' : 'Save Changes' }}</button>
          <button @click="currentMode = 'profile'" class="like-btn">Cancel</button>
        </div>
      </div>
    </div>

    <div v-if="showUploadModal" class="modal-overlay">
      <div class="modal-content">
        <h3>Post to Family Feed</h3>
        <input type="file" @change="onFeedFileSelected" accept="image/*" class="file-input"/>
        <textarea v-model="newCaption" placeholder="Write a caption (optional)..." class="modal-textarea"></textarea>
        <div class="form-group">
          <label class="modal-label">Add to Album (Optional)</label>
          <select v-model="selectedAlbumId" class="modal-select">
            <option :value="null">No Album (General Feed)</option>
            <option v-for="album in albums" :key="album.id" :value="album.id">{{ album.title }}</option>
          </select>
        </div>
        <div class="profile-actions">
          <button @click="handleUpload" :disabled="uploading" class="like-btn">{{ uploading ? 'Uploading...' : 'Post Photo' }}</button>
          <button @click="showUploadModal = false" class="like-btn">Cancel</button>
        </div>
      </div>
    </div>

    <div class="fab-container">
      <button class="fab-sub" @click="showUploadModal = true">📸</button>
      <button class="fab-main" @click="currentMode = currentMode === 'feed' ? 'profile' : 'feed'">
        {{ currentMode === 'feed' ? '👤' : '🖼️' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import {ref, onMounted} from 'vue';
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
const historicalPhotos = ref([]);

const currentView = ref('feed'); // 'feed' or 'albums'
const albums = ref([]);
const selectedAlbum = ref(null);
const selectedAlbumId = ref(null);
const albumPhotos = ref([]);

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

  if (selectedAlbumId.value) {
    formData.append('album_id', selectedAlbumId.value);
  }

  try {
    await api.post('/upload', formData);

    // Reset state only on success
    showUploadModal.value = false;
    newCaption.value = '';
    selectedFeedFile.value = null;
    fetchPhotos();
    fetchAlbums();
  } catch (err) {
    console.error("Upload failed:", err);
    alert("Upload failed. Please try again.");
  } finally {
    uploading.value = false;
  }
  selectedAlbumId.value = null; // Reset after upload
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

const fetchAlbums = async () => {
  try {
    const res = await api.get('/albums');
    albums.value = res.data;
  } catch (err) {
    console.error("Failed to fetch albums", err);
  }
};

const openAlbum = async (album) => {
  selectedAlbum.value = album;
  try {
    const res = await api.get(`/albums/${album.id}/photos`);
    albumPhotos.value = res.data;
  } catch (err) {
    console.error("Error loading album photos", err);
  }
};

const handleCreateAlbum = async () => {
  const title = prompt("Enter Album Name:");
  if (!title) return;

  const formData = new FormData();
  formData.append('title', title);

  try {
    const res = await api.post('/albums', formData);
    albums.value.push(res.data); // Your improved backend response makes this easy!
  } catch (err) {
    alert("Could not create album.");
  }
};

onMounted(async () => {
  fetchPhotos();
  fetchAlbums();
  try {
    const res = await api.get('/historical');
    historicalPhotos.value = res.data;
  } catch (err) {
    console.error("Historical fetch failed", err);
  }
});

// Helper for the label
const getYearAgoText = (dateString) => {
  if (!dateString) return "Sometime ago";
  const years = new Date().getFullYear() - new Date(dateString).getFullYear();
  if (years === 0) return "Less than a year ago";
  return `${years} year${years > 1 ? 's' : ''} ago`;
};
</script>

<style scoped>
/* Scoped overrides if needed; otherwise relies on style.css */
.user-container {
  padding-top: 20px;
}
</style>
