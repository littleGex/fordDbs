/* --- Photo Card Container --- */
.photo-card-container {
  background: #1f1f1f; /* Slightly lighter than main bg for card feel */
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
}

.feed-img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
}

.photo-card-content {
  padding: 16px;
}

/* --- Comment Input Alignment --- */
.comment-input-group {
  display: flex;
  border: 1px solid #333;
  border-radius: 4px;
  overflow: hidden;
  margin-top: 12px;
  background: #2b2b2b;
}

.comment-input-group input {
  flex: 1;
  border: none !important; /* Remove individual borders */
  background: transparent;
  padding: 10px 12px;
  font-size: 0.9rem;
  color: white;
}

.comment-input-group input:focus {
  outline: none;
}

.post-comment-btn {
  border: none !important;
  border-left: 1px solid #333 !important;
  background: transparent;
  color: #e50914;
  font-weight: 700;
  font-size: 0.85rem;
  padding: 0 15px;
  border-radius: 0;
}

.post-comment-btn:hover {
  background: rgba(229, 9, 20, 0.1);
}

/* --- View Icon Styling --- */
.view-stat {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #808080;
  font-size: 0.9rem;
}

.icon-svg {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
