<template>
  <div class="archive-container">
    <h2 class="archive-title">Family Archive</h2>

    <div class="photo-grid">
      <div v-for="photo in photos" :key="photo.id" class="photo-card">
        <img
          :src="photo.url"
          :alt="photo.caption"
          loading="lazy"
          @click="$emit('photo-click', photo)"
        />
        <div class="photo-info">
          <p>{{ photo.caption }}</p>
          <small v-if="photo.uploader">By {{ photo.uploader.display_name }}</small>
        </div>
      </div>
    </div>

    <div class="pagination-controls">
      <button v-if="hasMore && !loading" @click="loadMore" class="btn-load-more">
        Load More
      </button>
      <p v-if="loading">Loading memories...</p>
      <p v-if="!hasMore" class="end-text">End of the line! 📸</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api/axios';

const emit = defineEmits(['photo-click']); // Crucial for the zoom to work!
const photos = ref([]);
const skip = ref(0);
const limit = 20;
const loading = ref(false);
const hasMore = ref(true);

const fetchPhotos = async () => {
  if (loading.value || !hasMore.value) return;
  loading.value = true;
  try {
    // Note: ensure no '/photos' prefix if your backend router is /archive
    const response = await api.get(`/archive?skip=${skip.value}&limit=${limit}`);
    const newPhotos = response.data;
    photos.value.push(...newPhotos);
    if (newPhotos.length < limit) hasMore.value = false;
    skip.value += limit;
  } catch (err) {
    console.error("Archive fetch error", err);
  } finally {
    loading.value = false;
  }
};

onMounted(fetchPhotos);
const loadMore = fetchPhotos;
</script>

<style scoped>
.archive-container {
  padding: 20px 4%;
  max-width: 1400px;
  margin: 0 auto;
}

.archive-title {
  margin-bottom: 20px;
  font-size: 1.5rem;
  font-weight: 600;
}

.photo-card img {
  width: 100%;
  height: 250px;
  object-fit: cover; /* Use 'cover' for the Netflix-grid look, 'contain' if you want no cropping */
  border-radius: 8px;
  cursor: zoom-in;
  transition: transform 0.2s;
}

.photo-card img:hover {
  transform: scale(1.02);
}

.pagination-controls {
  text-align: center;
  padding: 40px 0;
}

.btn-load-more {
  background-color: #e50914;
  color: white;
  border: none;
  padding: 12px 30px;
  font-size: 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: bold;
}

.btn-load-more:hover {
  background-color: #b20710;
}

.end-text, .loading-text {
  color: #888;
  font-style: italic;
}
</style>
