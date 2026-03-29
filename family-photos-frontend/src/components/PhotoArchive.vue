<template>
  <div class="archive-container">
    <h2>Family Archive</h2>

    <div class="photo-grid">
      <div v-for="photo in photos" :key="photo.id" class="photo-card">
        <img
            :src="photo.url"
            @click="handlePhotoClick(photo)"
            style="cursor: zoom-in"
            :alt="photo.caption"
            loading="lazy"
            draggable="false"
            @contextmenu.prevent
        />
        <div class="photo-info">
          <p>{{ photo.caption }}</p>
          <small>By {{ photo.uploader.display_name }}</small>
        </div>
      </div>
    </div>

    <div class="pagination-controls">
      <p v-if="loading" class="loading-text">Loading memories...</p>

      <button
          v-if="hasMore && !loading"
          @click="loadMore"
          class="btn-load-more"
      >
        Load More
      </button>

      <p v-if="!hasMore && photos.length > 0" class="end-text">
        You've reached the end of the archive! 📸
      </p>
    </div>
  </div>
</template>

<script setup>
import {ref, onMounted} from 'vue';
import api from '../api/axios'; // Adjust path if needed

const photos = ref([]);
const skip = ref(0);
const limit = 20; // How many to fetch per click
const loading = ref(false);
const hasMore = ref(true); // Assumes we have photos until the API returns fewer than 20

const emit = defineEmits(['photo-click'])

const fetchPhotos = async () => {
  if (loading.value || !hasMore.value) return;

  loading.value = true;
  try {
    const response = await api.get(`/archive?skip=${skip.value}&limit=${limit}`);
    const newPhotos = response.data;

    // Append the new photos to our existing array
    photos.value.push(...newPhotos);

    // If the backend returned fewer photos than our limit, we hit the end
    if (newPhotos.length < limit) {
      hasMore.value = false;
    } else {
      // Otherwise, prepare the skip counter for the next click
      skip.value += limit;
    }
  } catch (error) {
    console.error("Failed to load archive:", error);
  } finally {
    loading.value = false;
  }
};

const handlePhotoClick = (photo) => {
  emit('photo-click', photo);
}

// Fetch the first batch when the component loads
onMounted(() => {
  fetchPhotos();
});

const loadMore = () => {
  fetchPhotos();
};
</script>

<style scoped>
.archive-container {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.photo-card img {
  width: 100%;
  height: 250px;
  object-fit: contain;
  background-color: #000;
  border-radius: 8px;
  /* Extra mobile protection against selection */
  user-select: none;
  -webkit-touch-callout: none;
}

.pagination-controls {
  text-align: center;
  padding: 20px 0;
}

.btn-load-more {
  background-color: #e50914; /* Netflix Red */
  color: white;
  border: none;
  padding: 10px 20px;
  font-size: 1rem;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.btn-load-more:hover {
  background-color: #b20710;
}

.end-text, .loading-text {
  color: #888;
  font-style: italic;
}
</style>
