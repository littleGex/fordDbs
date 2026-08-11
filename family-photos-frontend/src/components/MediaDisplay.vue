<template>
  <video
    v-if="photo.media_type === 'video' && controls"
    :src="photo.url"
    controls
    preload="metadata"
    playsinline
    @loadeddata="$emit('ready')"
    @click="$emit('click', $event)"
  />
  <video
    v-else-if="photo.media_type === 'video'"
    :src="photo.url"
    preload="metadata"
    muted
    @loadeddata="$emit('ready')"
    @click="$emit('click', $event)"
  />
  <img
    v-else
    :src="photo.url"
    loading="lazy"
    :alt="photo.caption || ''"
    @load="$emit('ready')"
    @click="$emit('click', $event)"
  />
</template>

<script setup>
// Renders a photo or a video (play-on-press with a native seek bar --
// no autoplay, no custom player) using whichever media_type the API
// reports. `controls` should only be true in the lightbox: a video
// with native controls in a grid thumbnail would make the play button
// intercept clicks meant to open the lightbox, so grid/thumbnail
// contexts get a plain, non-interactive preview instead (click opens
// the lightbox exactly like an image does).
defineProps({
  photo: { type: Object, required: true },
  controls: { type: Boolean, default: false }
});
defineEmits(['click', 'ready']);
</script>
