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
    @loadedmetadata="showFirstFrame"
    @seeked="$emit('ready')"
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

// preload="metadata" alone often leaves grid-thumbnail videos visually
// black (especially on iOS Safari) until playback starts -- there's no
// poster image, and metadata-only preload doesn't guarantee a decoded,
// painted frame. Seeking to a tiny offset once metadata is known forces
// the browser to decode and show that frame. Efficient because the
// transcode sets +faststart, enabling a range request for just that
// moment instead of downloading the whole file.
const showFirstFrame = (event) => {
  const video = event.target;
  video.currentTime = Math.min(0.1, (video.duration || 1) / 2);
};
</script>
