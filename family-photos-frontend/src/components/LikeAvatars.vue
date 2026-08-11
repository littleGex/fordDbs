<template>
  <div class="like-summary" v-if="likes.length" @click="showModal = true">
    <div class="avatar-stack">
      <img
        v-for="(user, i) in visibleLikes"
        :key="user.id"
        :src="getAvatar(user)"
        class="stack-avatar"
        :style="{ zIndex: visibleLikes.length - i }"
        :alt="user.display_name"
      />
      <div v-if="overflowCount > 0" class="stack-avatar overflow-bubble">
        +{{ overflowCount }}
      </div>
    </div>
    <span class="like-text">{{ summaryText }}</span>
  </div>

  <Teleport to="body">
    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
      <div class="modal-content likers-modal">
        <div class="modal-header">
          <h3>Liked by</h3>
          <button class="close-modal-btn" @click="showModal = false">✕</button>
        </div>
        <div class="likers-list">
          <div v-for="user in likes" :key="user.id" class="liker-row">
            <img :src="getAvatar(user)" class="liker-avatar" />
            <span>{{ user.display_name }}</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, ref } from 'vue';
import { getAvatar } from '../utils/avatar';

const props = defineProps({
  likes: { type: Array, default: () => [] } // [{ id, display_name, profile_photo_url }]
});

const showModal = ref(false);
const MAX_VISIBLE = 3;

const visibleLikes = computed(() => props.likes.slice(0, MAX_VISIBLE));
const overflowCount = computed(() => Math.max(0, props.likes.length - MAX_VISIBLE));

const summaryText = computed(() => {
  const names = props.likes.map(u => u.display_name);
  if (names.length === 1) return `Liked by ${names[0]}`;
  if (names.length === 2) return `Liked by ${names[0]} and ${names[1]}`;
  const rest = names.length - 2;
  return `Liked by ${names[0]}, ${names[1]} and ${rest} other${rest > 1 ? 's' : ''}`;
});
</script>

<style scoped>
.like-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 0;
}

.avatar-stack {
  display: flex;
}

.stack-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid #141414;
  object-fit: cover;
  margin-left: -8px;
}

.stack-avatar:first-child {
  margin-left: 0;
}

.overflow-bubble {
  background: #333;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.65rem;
  font-weight: 600;
}

.like-text {
  font-size: 0.85rem;
  color: #ccc;
}

/* Bottom-sheet style modal — feels native on mobile */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  z-index: 4000;
}

.modal-content.likers-modal {
  background: #141414;
  width: 100%;
  max-width: 480px;
  max-height: 70vh;
  border-radius: 16px 16px 0 0;
  padding: 20px;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.close-modal-btn {
  background: none;
  border: none;
  color: #ccc;
  font-size: 1.2rem;
  cursor: pointer;
}

.liker-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #2b2b2b;
}

.liker-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
}
</style>
