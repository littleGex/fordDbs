<template>
  <div class="messages-layout">
    <div class="conversation-list" :class="{ 'show-mobile': !selectedConversation }">
      <div class="list-header">
        <h2 class="section-title">Messages</h2>
        <button class="new-msg-btn" @click="openNewConversationModal" title="New Message">✏️</button>
      </div>

      <div v-if="loadingConversations" class="empty-state">Loading conversations...</div>
      <div v-else-if="conversations.length === 0" class="empty-state">
        No conversations yet. Start one with the ✏️ button above.
      </div>

      <div
          v-for="conv in sortedConversations"
          :key="conv.id"
          class="conversation-row"
          :class="{ active: selectedConversation?.id === conv.id }"
          @click="selectConversation(conv)"
      >
        <img :src="conversationAvatar(conv)" class="conv-avatar" />
        <div class="conv-info">
          <div class="conv-title-row">
            <span class="conv-title">{{ conversationTitle(conv) }}</span>
            <span v-if="conv.last_message" class="conv-time">{{ formatTime(conv.last_message.created_at) }}</span>
          </div>
          <p class="conv-preview">{{ previewText(conv) }}</p>
        </div>
        <span v-if="conv.unread_count > 0" class="unread-badge">{{ conv.unread_count }}</span>
      </div>
    </div>

    <div class="thread-panel" :class="{ 'show-mobile': selectedConversation }">
      <template v-if="selectedConversation">
        <div class="thread-header">
          <button class="back-btn mobile-only" @click="deselectConversation">← Back</button>
          <img :src="conversationAvatar(selectedConversation)" class="conv-avatar" />
          <div class="thread-header-info">
            <span class="conv-title">{{ conversationTitle(selectedConversation) }}</span>
            <span class="member-count" v-if="selectedConversation.is_group">
              {{ selectedConversation.member_ids.length }} members
            </span>
          </div>
          <button class="leave-btn" @click="handleLeave">Leave</button>
        </div>

        <div class="thread-messages" ref="threadEl">
          <div v-if="loadingMessages" class="empty-state">Loading...</div>
          <div
              v-for="msg in messages"
              :key="msg.id"
              class="message-row"
              :class="{ mine: msg.sender_id === auth.currentUser.id }"
          >
            <div class="bubble" :class="{ mine: msg.sender_id === auth.currentUser.id, deleted: msg.deleted }">
              <div v-if="selectedConversation.is_group && msg.sender_id !== auth.currentUser.id" class="sender-name">
                {{ senderName(msg.sender_id) }}
              </div>
              <img v-if="msg.photo_url && !msg.deleted" :src="msg.photo_url" class="bubble-photo" />
              <p v-if="msg.deleted" class="deleted-text">Message deleted</p>
              <p v-else-if="msg.body">{{ msg.body }}</p>
              <div class="bubble-footer">
                <span class="bubble-time">{{ formatTime(msg.created_at) }}</span>
                <button
                    v-if="!msg.deleted && canDelete(msg)"
                    class="delete-msg-btn"
                    @click="handleDeleteMessage(msg)"
                    title="Delete message"
                >✕</button>
              </div>
            </div>
          </div>
        </div>

        <div class="compose-bar">
          <input
              v-model="composeText"
              placeholder="Write a message..."
              @keyup.enter="handleSend"
              :disabled="sending"
          />
          <button class="btn-primary" @click="handleSend" :disabled="sending || !composeText.trim()">Send</button>
        </div>
      </template>

      <div v-else class="empty-state thread-empty">
        Select a conversation, or start a new one.
      </div>
    </div>

    <div v-if="showNewModal" class="modal-overlay" @click.self="showNewModal = false">
      <div class="modal-content">
        <div class="modal-header">
          <h3>New Message</h3>
          <button class="close-modal-btn" @click="showNewModal = false">✕</button>
        </div>

        <div class="modal-body user-picker">
          <label v-for="user in otherUsers" :key="user.id" class="user-pick-row">
            <input type="checkbox" v-model="newMembers" :value="user.id" />
            <img :src="getAvatar(user)" class="conv-avatar small" />
            <span>{{ user.display_name || user.username }}</span>
          </label>
        </div>

        <div class="modal-body" v-if="newMembers.length > 1">
          <input v-model="newGroupTitle" placeholder="Group name (optional)" class="styled-input" />
        </div>

        <div class="modal-footer">
          <button class="btn-secondary" @click="showNewModal = false">Cancel</button>
          <button class="btn-primary" :disabled="newMembers.length === 0" @click="handleStartConversation">
            Start
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { useAuthStore } from '../stores/auth';
import { useMessagingStore } from '../stores/messaging';
import familyPhotosApi from '../api/axios';
import messagingApi from '../api/messagingApi';
import { getAvatar } from '../utils/avatar';

const auth = useAuthStore();
const store = useMessagingStore();

// Conversations, unread counts, and the live WebSocket connection all
// live in the shared store (NavBar's unread badge reads the same data),
// so this view just reflects it rather than keeping its own copy.
const conversations = computed(() => store.conversations);
const loadingConversations = computed(() => store.loadingConversations);
const selectedConversation = ref(null);
const messages = ref([]);
const loadingMessages = ref(false);
const composeText = ref('');
const sending = ref(false);
const threadEl = ref(null);

const familyUsers = ref([]);
const usersById = computed(() => {
  const map = {};
  for (const u of familyUsers.value) map[u.id] = u;
  return map;
});
const otherUsers = computed(() =>
  familyUsers.value.filter(u => u.id !== auth.currentUser.id)
);

const showNewModal = ref(false);
const newMembers = ref([]);
const newGroupTitle = ref('');

const sortedConversations = computed(() =>
  [...conversations.value].sort((a, b) => {
    const aTime = a.last_message?.created_at || 0;
    const bTime = b.last_message?.created_at || 0;
    return new Date(bTime) - new Date(aTime);
  })
);

const otherMemberIds = (conv) => conv.member_ids.filter(id => id !== auth.currentUser.id);

const conversationTitle = (conv) => {
  if (conv.is_group) return conv.title || 'Group chat';
  const otherId = otherMemberIds(conv)[0];
  const user = usersById.value[otherId];
  return user?.display_name || user?.username || 'Unknown';
};

const conversationAvatar = (conv) => {
  if (conv.is_group) return getAvatar({ display_name: conv.title || 'Group' });
  const otherId = otherMemberIds(conv)[0];
  return getAvatar(usersById.value[otherId]);
};

const senderName = (userId) => usersById.value[userId]?.display_name || 'Unknown';

const previewText = (conv) => {
  if (!conv.last_message) return 'No messages yet';
  if (conv.last_message.deleted) return 'Message deleted';
  return conv.last_message.body || (conv.last_message.photo_url ? '📷 Photo' : '');
};

const formatTime = (isoString) => {
  if (!isoString) return '';
  const date = new Date(isoString + (isoString.endsWith('Z') ? '' : 'Z'));
  const isToday = date.toDateString() === new Date().toDateString();
  if (isToday) return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
};

const canDelete = (msg) => {
  if (msg.sender_id !== auth.currentUser.id && auth.currentUser.role !== 'parent') return false;
  if (auth.currentUser.role === 'parent') return true;
  const created = new Date(msg.created_at + (msg.created_at.endsWith('Z') ? '' : 'Z'));
  return (Date.now() - created.getTime()) < 24 * 60 * 60 * 1000;
};

const scrollToBottom = () => {
  nextTick(() => {
    if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight;
  });
};

const fetchFamilyUsers = async () => {
  try {
    const res = await familyPhotosApi.get('/users');
    familyUsers.value = res.data;
  } catch (err) {
    console.error('Failed to fetch family users', err);
  }
};

const selectConversation = async (conv) => {
  selectedConversation.value = conv;
  store.setActiveConversation(conv.id);
  loadingMessages.value = true;
  messages.value = [];
  try {
    const res = await messagingApi.get(`/conversations/${conv.id}/messages`);
    messages.value = res.data;
    scrollToBottom();
    await markRead(conv);
  } catch (err) {
    console.error('Failed to fetch messages', err);
  } finally {
    loadingMessages.value = false;
  }
};

const deselectConversation = () => {
  selectedConversation.value = null;
  store.setActiveConversation(null);
};

const markRead = async (conv) => {
  if (messages.value.length === 0) return;
  const lastId = messages.value[messages.value.length - 1].id;
  await store.markRead(conv.id, lastId);
};

// The active conversation's last_message is updated live by the store's
// WebSocket handler; watch it to append incoming messages to the open
// thread (the id check also skips the echo of a message we just sent
// ourselves in handleSend, which already pushed it locally).
watch(
  () => conversations.value.find(c => c.id === selectedConversation.value?.id)?.last_message,
  (msg) => {
    if (!msg || !selectedConversation.value) return;
    if (messages.value.some(m => m.id === msg.id)) return;
    messages.value.push(msg);
    scrollToBottom();
    markRead(selectedConversation.value);
  }
);

const toFormData = (obj) => {
  const fd = new FormData();
  for (const [key, value] of Object.entries(obj)) {
    if (value !== undefined && value !== null) fd.append(key, value);
  }
  return fd;
};

const handleSend = async () => {
  const body = composeText.value.trim();
  if (!body || sending.value || !selectedConversation.value) return;

  sending.value = true;
  const clientId = crypto.randomUUID();
  try {
    const res = await messagingApi.post(
      `/conversations/${selectedConversation.value.id}/messages`,
      toFormData({ client_id: clientId, body })
    );
    messages.value.push(res.data);
    composeText.value = '';
    scrollToBottom();

    const local = conversations.value.find(c => c.id === selectedConversation.value.id);
    if (local) local.last_message = res.data;
  } catch (err) {
    console.error('Send failed', err);
    alert('Could not send message. Please try again.');
  } finally {
    sending.value = false;
  }
};

const handleDeleteMessage = async (msg) => {
  if (!confirm('Delete this message?')) return;
  try {
    await messagingApi.delete(`/messages/${msg.id}`);
    msg.deleted = true;
    msg.body = null;
    msg.photo_url = null;
  } catch (err) {
    alert(err.response?.data?.detail || 'Could not delete message');
  }
};

const handleLeave = async () => {
  if (!confirm('Leave this conversation?')) return;
  const conv = selectedConversation.value;
  try {
    await messagingApi.post(`/conversations/${conv.id}/leave`);
    store.removeConversation(conv.id);
    deselectConversation();
  } catch (err) {
    alert(err.response?.data?.detail || 'Could not leave conversation');
  }
};

const openNewConversationModal = () => {
  newMembers.value = [];
  newGroupTitle.value = '';
  showNewModal.value = true;
};

const handleStartConversation = async () => {
  // For a plain 1:1 DM, reuse an existing conversation instead of
  // spawning a duplicate every time -- the backend doesn't dedupe this
  // itself since it also needs to support creating fresh groups.
  if (newMembers.value.length === 1) {
    const targetId = newMembers.value[0];
    const existing = conversations.value.find(
      c => !c.is_group && c.member_ids.length === 2 && c.member_ids.includes(targetId)
    );
    if (existing) {
      showNewModal.value = false;
      selectConversation(existing);
      return;
    }
  }

  try {
    const res = await messagingApi.post('/conversations', toFormData({
      is_group: newMembers.value.length > 1,
      title: newGroupTitle.value || null,
      member_ids: newMembers.value.join(','),
    }));
    showNewModal.value = false;
    await store.fetchConversations();
    const created = conversations.value.find(c => c.id === res.data.id);
    if (created) selectConversation(created);
  } catch (err) {
    alert('Could not start conversation');
  }
};

onMounted(async () => {
  store.init();
  await fetchFamilyUsers();
});

onUnmounted(() => {
  store.setActiveConversation(null);
});
</script>

<style scoped>
.messages-layout {
  display: flex;
  height: calc(100vh - 90px);
  max-width: 1400px;
  margin: 0 auto;
  border: 1px solid #222;
  border-radius: 8px;
  overflow: hidden;
}

/* --- Conversation List --- */
.conversation-list {
  width: 340px;
  flex-shrink: 0;
  border-right: 1px solid #222;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #222;
}

.new-msg-btn {
  background: none;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
}

.conversation-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  cursor: pointer;
  position: relative;
  transition: background 0.2s;
}

.conversation-row:hover {
  background: rgba(255, 255, 255, 0.05);
}

.conversation-row.active {
  background: rgba(255, 255, 255, 0.08);
}

.conv-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}

.conv-avatar.small {
  width: 32px;
  height: 32px;
}

.conv-info {
  flex: 1;
  min-width: 0;
}

.conv-title-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}

.conv-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  font-size: 0.75rem;
  color: #888;
  flex-shrink: 0;
}

.conv-preview {
  margin: 2px 0 0;
  font-size: 0.85rem;
  color: #999;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.unread-badge {
  background: var(--accent, #e50914);
  color: white;
  font-size: 0.7rem;
  font-weight: 700;
  border-radius: 999px;
  min-width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
}

.empty-state {
  padding: 40px 20px;
  color: #888;
  text-align: center;
}

/* --- Thread Panel --- */
.thread-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.thread-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid #222;
}

.thread-header-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.member-count {
  font-size: 0.75rem;
  color: #888;
}

.leave-btn {
  background: none;
  border: 1px solid #444;
  color: #bbb;
  border-radius: 6px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 0.8rem;
}

.leave-btn:hover {
  border-color: #666;
  color: #fff;
}

.mobile-only {
  display: none;
}

.thread-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.thread-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-row {
  display: flex;
}

.message-row.mine {
  justify-content: flex-end;
}

.bubble {
  max-width: 65%;
  background: #2b2b2b;
  border-radius: 14px;
  padding: 8px 14px;
}

.bubble.mine {
  background: var(--accent, #e50914);
}

.bubble.deleted {
  background: transparent;
  border: 1px dashed #444;
}

.sender-name {
  font-size: 0.75rem;
  font-weight: 600;
  color: #ccc;
  margin-bottom: 2px;
}

.bubble p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.deleted-text {
  font-style: italic;
  color: #888;
}

.bubble-photo {
  max-width: 100%;
  border-radius: 8px;
  margin-bottom: 6px;
}

.bubble-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 2px;
}

.bubble-time {
  font-size: 0.65rem;
  opacity: 0.7;
}

.delete-msg-btn {
  background: none;
  border: none;
  color: inherit;
  opacity: 0.6;
  cursor: pointer;
  font-size: 0.7rem;
  padding: 0;
}

.delete-msg-btn:hover {
  opacity: 1;
}

.compose-bar {
  display: flex;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid #222;
}

.compose-bar input {
  flex: 1;
  padding: 10px 14px;
  background: #2b2b2b;
  border: 1px solid #444;
  border-radius: 20px;
  color: white;
}

.compose-bar input:focus {
  outline: none;
  border-color: var(--accent, #e50914);
}

/* --- New conversation modal --- */
.user-picker {
  max-height: 300px;
  overflow-y: auto;
  text-align: left;
}

.user-pick-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  cursor: pointer;
}

/* --- Mobile: single-pane, toggled by selection --- */
@media (max-width: 768px) {
  .messages-layout {
    height: calc(100vh - 65px);
    border: none;
    border-radius: 0;
  }

  .conversation-list,
  .thread-panel {
    display: none;
    width: 100%;
  }

  .conversation-list.show-mobile,
  .thread-panel.show-mobile {
    display: flex;
  }

  .mobile-only {
    display: inline-block;
  }
}
</style>
