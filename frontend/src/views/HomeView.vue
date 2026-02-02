<script setup>
import {ref, watch, onMounted} from 'vue'
import axios from 'axios'

const children = ref([])
const selectedChild = ref(null)
const recentTransactions = ref([])
const wishes = ref([])
const withdrawAmount = ref(0)
const API_BASE = import.meta.env.VITE_API_BASE;
const showWishForm = ref(false)
const newWish = ref({name: '', cost: 0})
const childStats = ref({})

// Fetches the count of "Goal Met" transactions
const fetchStats = async (childId) => {
  try {
    const res = await axios.get(`${API_BASE}/stats/${childId}`)
    childStats.value[childId] = res.data.wishes_bought
  } catch (e) {
    childStats.value[childId] = 0
  }
}

const fetchChildren = async () => {
  try {
    const res = await axios.get(`${API_BASE}/children`)
    children.value = res.data

    // Fetch trophies for every child immediately
    children.value.forEach(child => fetchStats(child.id))

    if (children.value.length > 0 && !selectedChild.value) {
      selectedChild.value = children.value[0]
    }
  } catch (e) {
    console.error("Error fetching children:", e)
  }
}

watch(selectedChild, async (newChild) => {
  if (newChild) {
    try {
      const [histRes, wishRes] = await Promise.all([
        axios.get(`${API_BASE}/history/${newChild.id}?limit=5`),
        axios.get(`${API_BASE}/wishes/${newChild.id}`)
      ])
      recentTransactions.value = histRes.data
      wishes.value = wishRes.data
    } catch (e) {
      console.error("Error fetching child data:", e)
    }
  }
})

const getProgress = (cost) => {
  if (!selectedChild.value || cost <= 0) return 0
  const percent = (selectedChild.value.balance / cost) * 100
  return Math.min(percent, 100).toFixed(0)
}

const confirmWithdraw = async () => {
  if (!selectedChild.value || withdrawAmount.value <= 0) return
  if (confirm(`Confirm withdrawal of €${withdrawAmount.value.toFixed(2)}?`)) {
    await axios.post(`${API_BASE}/withdraw/${selectedChild.value.id}`, null, {
      params: {
        amount: withdrawAmount.value,
        description: "Dashboard Withdrawal",
        category: "Spend"
      }
    })
    withdrawAmount.value = 0
    fetchChildren()
  }
}

const submitWish = async () => {
  if (!newWish.value.name || newWish.value.cost <= 0) return
  await axios.post(`${API_BASE}/wish/${selectedChild.value.id}`, null, {
    params: {item_name: newWish.value.name, cost: newWish.value.cost}
  })
  newWish.value = {name: '', cost: 0}
  showWishForm.value = false
  const wishRes = await axios.get(`${API_BASE}/wishes/${selectedChild.value.id}`)
  wishes.value = wishRes.data
}

const calculateAge = (birthdayStr) => {
  if (!birthdayStr) return 0;
  const birthDate = new Date(birthdayStr);
  const today = new Date();
  let age = today.getFullYear() - birthDate.getFullYear();
  const m = today.getMonth() - birthDate.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
    age--;
  }
  return age;
};

// Calculate % of the year completed until next birthday
const getBirthdayProgress = (birthdayStr) => {
  if (!birthdayStr) return 0;
  const today = new Date();
  const birthDate = new Date(birthdayStr);

  // Set next birthday date
  let nextBirthday = new Date(today.getFullYear(), birthDate.getMonth(), birthDate.getDate());

  // If birthday already passed this year, set it to next year
  if (today > nextBirthday) {
    nextBirthday.setFullYear(today.getFullYear() + 1);
  }

  const lastBirthday = new Date(nextBirthday.getFullYear() - 1, birthDate.getMonth(), birthDate.getDate());

  const totalMs = nextBirthday - lastBirthday;
  const elapsedMs = today - lastBirthday;

  return Math.min(100, Math.max(0, (elapsedMs / totalMs) * 100));
};

onMounted(fetchChildren)
</script>

<template>
  <div class="dashboard-container">
    <nav class="child-nav" v-if="children.length">
      <button
          v-for="c in children"
          :key="c.id"
          :class="{ active: selectedChild?.id === c.id }"
          @click="selectedChild = c"
      >
        <span class="name-text">{{ c.name }}</span>
        <span class="nav-trophy">
          🏆 {{ childStats[c.id] || 0 }}
        </span>
      </button>
    </nav>

    <div v-if="selectedChild" class="dashboard-grid">
      <div class="tile balance-tile">
        <h3>Current Balance</h3>
        <div class="big-money">€{{ selectedChild.balance.toFixed(2) }}</div>

        <div class="withdraw-section">
          <h4>Withdraw Cash</h4>
          <div class="quick-amounts">
            <button v-for="amt in [0.5, 1, 2, 5]" :key="amt" @click="withdrawAmount = amt">
              €{{ amt.toFixed(2) }}
            </button>
          </div>
          <div class="unified-withdraw-group">
            <div class="input-wrapper">
              <span class="currency-prefix">€</span>
              <input v-model.number="withdrawAmount" type="number" step="0.10" placeholder="0.00">
            </div>
            <button class="btn-withdraw-main" @click="confirmWithdraw" :disabled="withdrawAmount <= 0">
              Withdraw
            </button>
          </div>
        </div>
      </div>

      <div class="id-card-tile" v-if="selectedChild && selectedChild.birth_date">
        <div class="card-header">
          <span class="chip">Level {{ calculateAge(selectedChild.birth_date) }} Member</span>
          <span class="emoji">🎁</span>
        </div>

        <div class="card-body">
          <div class="id-row">
            <span class="id-label">NAME</span>
            <span class="id-value">{{ selectedChild.name }}</span>
          </div>

          <div class="id-stats">
            <div class="id-row">
              <span class="id-label">CURRENT AGE</span>
              <span class="id-value">{{ calculateAge(selectedChild.birth_date) }}</span>
            </div>
            <div class="id-row">
              <span class="id-label">WEEKLY PAY</span>
              <span class="id-value">€{{ (calculateAge(selectedChild.birth_date) * 0.5).toFixed(2) }}</span>
            </div>
          </div>

          <div class="progress-section">
            <div class="progress-header">
              <span class="id-label">PROGRESS TO AGE {{ calculateAge(selectedChild.birth_date) + 1 }}</span>
              <span class="progress-pct">{{ Math.round(getBirthdayProgress(selectedChild.birth_date)) }}%</span>
            </div>
            <div class="progress-bar-bg">
              <div class="progress-bar-fill"
                   :style="{ width: getBirthdayProgress(selectedChild.birth_date) + '%' }"></div>
            </div>
          </div>
        </div>

        <div class="card-footer">
          <p>🗓️ Next Payout: Friday @ 07:30</p>
        </div>
      </div>

      <div class="tile wish-tile">
        <div class="tile-header">
          <h3>Wish List & Goals</h3>
          <button @click="showWishForm = !showWishForm" class="btn-add-inline">
            {{ showWishForm ? '−' : '+' }}
          </button>
        </div>

        <div v-if="showWishForm" class="wish-form-overlay">
          <input v-model="newWish.name" placeholder="What are you saving for?">
          <input v-model.number="newWish.cost" type="number" placeholder="Cost €">
          <button @click="submitWish" class="btn-save-wish">Set Goal</button>
        </div>

        <div v-if="wishes.length === 0" class="empty-state">
          No goals set yet. Click + to add one!
        </div>

        <div v-for="wish in wishes" :key="wish.id" class="wish-item">
          <div class="wish-info">
            <span class="wish-name">{{ wish.item_name }}</span>
            <span class="wish-cost">€{{ wish.cost.toFixed(2) }}</span>
          </div>
          <div class="progress-container">
            <div class="progress-bar" :style="{ width: getProgress(wish.cost) + '%' }"></div>
            <span class="progress-text">{{ getProgress(wish.cost) }}%</span>
          </div>
          <p v-if="getProgress(wish.cost) >= 100" class="goal-met-text">
            🎉 You saved enough! Ask for this.
          </p>
        </div>
      </div>

      <div class="tile history-tile">
        <div class="tile-header"><h3>Recent Activity</h3></div>
        <ul class="transaction-list">
          <li v-for="tx in recentTransactions" :key="tx.id">
            <div class="tx-info">
              <span class="tx-desc">{{ tx.description }}</span>
              <small class="tx-cat">{{ tx.category }}</small>
            </div>
            <span :class="['tx-amount', tx.amount < 0 ? 'minus' : 'plus']">
              {{ tx.amount < 0 ? '-' : '+' }} €{{ Math.abs(tx.amount).toFixed(2) }}
            </span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.child-nav {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-bottom: 30px;
}

.child-nav button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-width: 130px;
  padding: 12px 24px;
  border: none;
  border-radius: 30px;
  background: white;
  font-weight: bold;
  cursor: pointer;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
  transition: all 0.2s;
}

.child-nav button.active {
  background: #4a90e2;
  color: white;
  transform: translateY(-2px);
}

@media (max-width: 480px) {
  .child-nav {
    flex-wrap: wrap; /* Allows buttons to drop to a second row if needed */
  }
  .child-nav button {
    flex: 1; /* Makes buttons grow to fill the width */
    min-width: 120px;
  }
}

.nav-trophy {
  background: #fff9db;
  color: #fab005;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.8rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.active .nav-trophy {
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 25px;
  align-items: start;
}

@media (max-width: 768px) {
  .dashboard-grid {
    grid-template-columns: 1fr; /* Stack everything in one column */
    gap: 15px; /* Slightly tighter spacing for mobile */
  }

  .id-card-tile {
    max-width: 100%; /* Allow ID card to fill the screen width */
    margin: 10px 0;
  }

  .big-money {
    font-size: 2.8rem; /* Slightly smaller text so it doesn't wrap */
  }
}

.tile {
  background: white;
  padding: 25px;
  border-radius: 20px;
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.04);
  margin-bottom: 20px;
}

.big-money {
  font-size: 3.5rem;
  color: #2d3436;
  font-weight: 800;
  margin-bottom: 20px;
}

.withdraw-section {
  border-top: 1px solid #f1f2f6;
  padding-top: 20px;
}

.quick-amounts {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  margin-bottom: 15px;
}

.quick-amounts button {
  padding: 8px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-weight: bold;
  cursor: pointer;
  background: white;
}

.unified-withdraw-group {
  display: flex;
  height: 48px;
  margin-top: 15px;
}

.input-wrapper {
  flex: 1;
  position: relative;
}

.currency-prefix {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  font-weight: bold;
  color: #747d8c;
}

.input-wrapper input {
  width: 100%;
  height: 100%;
  padding: 0 12px 0 35px;
  border: 2px solid #f1f2f6;
  border-radius: 12px 0 0 12px;
  font-size: 1.1rem;
  box-sizing: border-box;
  outline: none;
}

.btn-withdraw-main {
  padding: 0 25px;
  background: #2ed573;
  color: white;
  border: none;
  border-radius: 0 12px 12px 0;
  font-weight: bold;
  cursor: pointer;
}

.wish-item {
  margin-bottom: 25px;
  border-bottom: 1px solid #f9f9f9;
  padding-bottom: 15px;
}

.wish-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-weight: 600;
}

.progress-container {
  height: 24px;
  background: #f1f2f6;
  border-radius: 12px;
  position: relative;
  overflow: hidden;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.1);
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4a90e2, #2ed573);
  transition: width 0.8s ease;
  border-radius: 12px;
}

.progress-text {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.75rem;
  font-weight: 800;
}

.goal-met-text {
  color: #2ed573;
  font-size: 0.85rem;
  font-weight: bold;
  margin-top: 5px;
}

.transaction-list {
  list-style: none;
  padding: 0;
}

.transaction-list li {
  display: flex;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid #f9f9f9;
}

@media (max-width: 480px) {
  .transaction-list li {
    font-size: 0.9rem;
  }
  .tx-desc {
    max-width: 150px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis; /* Adds "..." if the name is too long */
  }
}

.tx-info {
  display: flex;
  flex-direction: column;
}

.tx-cat {
  font-size: 0.7rem;
  color: #a0a0a0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.minus {
  color: #ff4757;
}

.plus {
  color: #2ed573;
}

.tile-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.btn-add-inline {
  background: #f1f2f6;
  border: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  cursor: pointer;
  font-weight: bold;
  font-size: 1.2rem;
}

.empty-state {
  text-align: center;
  color: #b2bec3;
  padding: 20px;
  font-style: italic;
}

.btn-save-wish {
  width: 100%;
  margin-top: 10px;
  padding: 12px;
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 10px;
  font-weight: bold;
  cursor: pointer;
}

.wish-form-overlay {
  background: #f8f9fa;
  padding: 15px;
  border-radius: 12px;
  margin-bottom: 20px;
  border: 1px solid #eee;
}

.wish-form-overlay input {
  width: 100%;
  padding: 10px;
  margin-bottom: 8px;
  border: 1px solid #ddd;
  border-radius: 8px;
  box-sizing: border-box;
}

.id-card-tile {
  background: linear-gradient(135deg, #6c5ce7 0%, #a29bfe 100%);
  color: white;
  border-radius: 20px;
  padding: 20px;
  box-shadow: 0 10px 20px rgba(108, 92, 231, 0.2);
  max-width: 350px;
  position: relative;
  overflow: hidden;
  margin: 20px auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.chip {
  background: rgba(255, 255, 255, 0.2);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: bold;
}

.id-label {
  display: block;
  font-size: 0.65rem;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.7);
  letter-spacing: 1px;
  margin-bottom: 2px;
}

.id-value {
  font-size: 1.2rem;
  font-weight: 700;
  display: block;
  margin-bottom: 15px;
}

.id-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 15px;
}

.id-value small {
  font-size: 0.8rem;
  font-weight: normal;
  margin-left: 2px;
}

.card-footer {
  margin-top: 10px;
  font-size: 0.75rem;
  background: rgba(0, 0, 0, 0.1);
  margin: 15px -20px -20px -20px;
  padding: 10px 20px;
  text-align: center;
}

.progress-section {
  margin-top: 15px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 5px;
}

.progress-pct {
  font-size: 0.7rem;
  font-weight: bold;
  color: rgba(255, 255, 255, 0.9);
}

.progress-bar-bg {
  height: 8px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
  width: 100%;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: #00cec9; /* A bright teal that pops against the purple */
  box-shadow: 0 0 10px rgba(0, 206, 201, 0.5);
  transition: width 0.5s ease-in-out;
}

.id-value small {
  font-size: 0.8rem;
  opacity: 0.8;
}
</style>
