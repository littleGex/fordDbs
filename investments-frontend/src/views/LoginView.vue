<script setup>
import {ref, onMounted} from 'vue'
import {useRouter} from 'vue-router'
import axios from 'axios'
import {AUTH_BASE, PARENT_ROLES, setSession} from '../auth'

const router = useRouter()
const users = ref([])
const selectedUserId = ref(null)
const password = ref('')
const errorMessage = ref('')
const loading = ref(false)

const fetchUsers = async () => {
  try {
    const res = await axios.get(`${AUTH_BASE}/login-options`)
    users.value = res.data
  } catch (e) {
    errorMessage.value = "Could not load the family list. Please try again."
  }
}

const submit = async () => {
  if (!selectedUserId.value || !password.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const res = await axios.post(`${AUTH_BASE}/login`, {
      user_id: selectedUserId.value,
      password: password.value
    })
    if (!PARENT_ROLES.includes(res.data.user.role)) {
      errorMessage.value = "Parents only"
      return
    }
    const picked = users.value.find(u => u.id === selectedUserId.value)
    setSession(res.data.access_token, {
      ...res.data.user,
      display_name: picked?.display_name
    })
    router.push('/')
  } catch (e) {
    // 403 carries the reason, e.g. an account still waiting for approval
    if (e.response?.status === 401) {
      errorMessage.value = "Wrong password!"
    } else if (e.response?.status === 403) {
      errorMessage.value = e.response.data.detail
    } else {
      errorMessage.value = "Login failed. Please try again."
    }
  } finally {
    password.value = ''
    loading.value = false
  }
}

onMounted(fetchUsers)
</script>

<template>
  <div class="login-container">
    <div class="tile login-tile">
      <h3>Parents only. Who are you?</h3>
      <div class="user-grid">
        <button
            v-for="u in users"
            :key="u.id"
            :class="{ active: selectedUserId === u.id }"
            @click="selectedUserId = u.id"
        >
          {{ u.display_name }}
        </button>
      </div>

      <form v-if="selectedUserId" @submit.prevent="submit">
        <input v-model="password" type="password" placeholder="Password"
               autocomplete="current-password">
        <button type="submit" class="btn-login" :disabled="loading || !password">
          Log in
        </button>
      </form>

      <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  max-width: 420px;
  margin: 40px auto;
  padding: 20px;
}

.tile {
  background: white;
  padding: 25px;
  border-radius: 20px;
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.04);
}

.user-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}

.user-grid button {
  padding: 12px;
  border: none;
  border-radius: 30px;
  background: #f1f2f6;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s;
}

.user-grid button.active {
  background: #4a90e2;
  color: white;
}

input {
  width: 100%;
  padding: 12px;
  margin-bottom: 10px;
  border: 2px solid #f1f2f6;
  border-radius: 12px;
  font-size: 1.1rem;
  box-sizing: border-box;
  outline: none;
}

.btn-login {
  width: 100%;
  padding: 12px;
  background: #2ed573;
  color: white;
  border: none;
  border-radius: 12px;
  font-weight: bold;
  cursor: pointer;
}

.btn-login:disabled {
  opacity: 0.6;
  cursor: default;
}

.error-text {
  color: #ff4757;
  font-weight: bold;
  margin: 15px 0 0;
}
</style>
