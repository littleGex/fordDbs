// stores/messaging.js
import { defineStore } from 'pinia';
import messagingApi, { MESSAGING_WS_BASE } from '../api/messagingApi';

// Shared across the whole app (NavBar badge + Messages.vue) so there's a
// single WebSocket connection and a single source of truth for unread
// counts, rather than each component tracking its own copy.
export const useMessagingStore = defineStore('messaging', {
  state: () => ({
    conversations: [],
    loadingConversations: true,
    activeConversationId: null,
    ws: null,
    initialized: false,
  }),
  getters: {
    unreadTotal: (state) =>
      state.conversations.reduce((sum, c) => sum + (c.unread_count || 0), 0),
  },
  actions: {
    // Safe to call from multiple mounted components (NavBar, Messages.vue) --
    // only does real work once per login session.
    init() {
      if (this.initialized) return;
      this.initialized = true;
      this.fetchConversations();
      this.connectWebSocket();
    },

    async fetchConversations() {
      try {
        const res = await messagingApi.get('/conversations');
        this.conversations = res.data;
      } catch (err) {
        console.error('Failed to fetch conversations', err);
      } finally {
        this.loadingConversations = false;
      }
    },

    setActiveConversation(conversationId) {
      this.activeConversationId = conversationId;
    },

    removeConversation(conversationId) {
      this.conversations = this.conversations.filter(c => c.id !== conversationId);
    },

    async markRead(conversationId, messageId) {
      try {
        const fd = new FormData();
        fd.append('message_id', messageId);
        await messagingApi.post(`/conversations/${conversationId}/read`, fd);
        const local = this.conversations.find(c => c.id === conversationId);
        if (local) local.unread_count = 0;
      } catch (err) {
        console.error('Failed to mark read', err);
      }
    },

    connectWebSocket() {
      const token = localStorage.getItem('token');
      if (!token) return;

      this.ws = new WebSocket(
        `${MESSAGING_WS_BASE}/ws?token=${encodeURIComponent(token)}`
      );

      this.ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type !== 'message') return;
        const msg = payload.data;

        const local = this.conversations.find(c => c.id === msg.conversation_id);
        if (local) {
          local.last_message = msg;
          // If Messages.vue has this conversation open, it marks the
          // message read itself as it appends it to the thread --
          // don't also bump the badge for it here.
          if (this.activeConversationId !== msg.conversation_id) {
            local.unread_count = (local.unread_count || 0) + 1;
          }
        }
      };

      // No reconnect/backoff for v1 -- a dropped socket just means live
      // delivery pauses until the page is reloaded; conversations/messages
      // are always fetchable normally in the meantime.
      this.ws.onerror = (err) => console.warn('Messaging socket error', err);
    },

    // Called on logout so a subsequent login (e.g. switching profiles on
    // a shared/kiosk browser) doesn't inherit the previous user's socket
    // or unread state.
    reset() {
      if (this.ws) this.ws.close();
      this.ws = null;
      this.conversations = [];
      this.loadingConversations = true;
      this.activeConversationId = null;
      this.initialized = false;
    },
  },
});
