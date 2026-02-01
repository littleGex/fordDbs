<script setup>
import {ref, onMounted, computed, watch} from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE;
const token = localStorage.getItem('admin_token')

const children = ref([])
const newChildName = ref('')

// Inline Edit State
const editingId = ref(null)
const newNameValue = ref('')

// Wish Management State
const selectedChildForWishes = ref(null)
const childWishes = ref([])
const newWish = ref({item_name: '', cost: 0})

// Adjustment Modal State
const activeAdjustId = ref(null)
const adjustAmount = ref(0)
const adjustReason = ref('')
const adjustCategory = ref('Reward')
const editingWishId = ref(null)
const editWishName = ref('')
const editWishCost = ref(0)
const newChildBirthDate = ref('')
const newBirthDateValue = ref('')

// Live Preview Logic
const currentChild = computed(() => children.value.find(c => c.id === activeAdjustId.value))
const previewBalance = computed(() => {
  const current = currentChild.value?.balance || 0
  const input = parseFloat(adjustAmount.value) || 0
  return {ifAdded: current + input, ifSubtracted: current - input}
})

const fetchChildren = async () => {
  try {
    const res = await axios.get(`${API_BASE}/children`)
    children.value = res.data
    if (children.value.length > 0 && !selectedChildForWishes.value) {
      selectedChildForWishes.value = children.value[0].id
    }
  } catch (e) {
    console.error("Failed to fetch children")
  }
}

const fetchWishes = async () => {
  if (!selectedChildForWishes.value) return
  try {
    const res = await axios.get(`${API_BASE}/wishes/${selectedChildForWishes.value}`)
    childWishes.value = res.data
  } catch (e) {
    childWishes.value = []
  }
}

watch(selectedChildForWishes, fetchWishes)

const buyWish = async (wish) => {
  const child = children.value.find(c => c.id === selectedChildForWishes.value)

  if (child.balance < wish.cost) {
    alert(`Not enough money! ${child.name} needs €${(wish.cost - child.balance).toFixed(2)} more.`)
    return
  }

  if (confirm(`Buy "${wish.item_name}" for €${wish.cost.toFixed(2)}?`)) {
    try {
      await axios.post(`${API_BASE}/withdraw/${child.id}`, null, {
        params: {
          amount: wish.cost,
          description: `Goal Achieved: ${wish.item_name}`,
          category: "Goal Met"
        }
      })

      await axios.delete(`${API_BASE}/wish/${wish.id}`)
      await fetchChildren()
      await fetchWishes()
    } catch (err) {
      alert("Something went wrong with the purchase.")
    }
  }
}

const handleUpdateWish = async (id) => {
  try {
    await axios.patch(`${API_BASE}/wish/${id}`, null, {
      params: {
        item_name: editWishName.value,
        cost: editWishCost.value
      }
    })
    editingWishId.value = null
    fetchWishes()
  } catch (e) {
    alert("Failed to update wish")
  }
}

const addChild = async () => {
  if (!newChildName.value) return
  await axios.post(`${API_BASE}/add-child/${newChildName.value}`, null, {
    params: {
      password: token,
      birth_date: newChildBirthDate.value
    }
  })
  newChildName.value = '';
  newChildBirthDate.value = ''; // Reset the date field
  fetchChildren()
}

const handleRename = async (id) => {
  await axios.patch(`${API_BASE}/child/${id}`, null, {
    params: {
      name: newNameValue.value,
      birth_date: newBirthDateValue.value, // Send the date to the backend
      password: token
    }
  })
  editingId.value = null;
  fetchChildren()
}

const deleteChild = async (id) => {
  if (confirm("Permanently delete child and history?")) {
    await axios.delete(`${API_BASE}/child/${id}`, {params: {password: token}})
    fetchChildren()
  }
}

const addWish = async () => {
  if (!newWish.value.item_name || newWish.value.cost <= 0) return
  await axios.post(`${API_BASE}/wish/${selectedChildForWishes.value}`, null, {
    params: {item_name: newWish.value.item_name, cost: newWish.value.cost}
  })
  newWish.value = {item_name: '', cost: 0}
  fetchWishes()
}

const deleteWish = async (wishId) => {
  await axios.delete(`${API_BASE}/wish/${wishId}`)
  fetchWishes()
}

const handleAdjustment = async (type) => {
  const finalAmount = type === 'add' ? Math.abs(adjustAmount.value) : -Math.abs(adjustAmount.value)
  await axios.post(`${API_BASE}/adjust/${activeAdjustId.value}`, null, {
    params: {
      amount: finalAmount,
      description: adjustReason.value || "Admin Adjustment",
      category: adjustCategory.value,
      password: token
    }
  })
  closeModal();
  fetchChildren()
}

const closeModal = () => {
  activeAdjustId.value = null;
  adjustAmount.value = 0;
  adjustReason.value = '';
}

onMounted(() => {
  fetchChildren()
})
</script>

<template>
  <div class="admin-view">
    <div class="tile">
      <h3>➕ Add New Child</h3>
      <div class="input-group">
        <input v-model="newChildName" placeholder="Name..." @keyup.enter="addChild">
        <input type="date" v-model="newChildBirthDate">
        <button @click="addChild" class="btn-success">Add Child</button>
      </div>
    </div>

    <div class="tile">
      <div class="tile-header">
        <h3>🏦 Manage Accounts</h3>
        <span class="badge">{{ children.length }} Active</span>
      </div>
      <table>
        <thead>
        <tr>
          <th>Name</th>
          <th>Balance</th>
          <th class="text-right">Actions</th>
        </tr>
        </thead>
        <tbody>
        <tr v-for="c in children" :key="c.id">
          <td>
            <div v-if="editingId === c.id" class="edit-group">
              <input v-model="newNameValue" class="small-input" @keyup.enter="handleRename(c.id)">
              <input type="date" v-model="newBirthDateValue" class="small-input">
              <button @click="handleRename(c.id)" class="btn-mini-save">OK</button>
            </div>
            <div v-else class="display-group">
              {{ c.name }}
              <small v-if="c.birth_date" style="color: #747d8c;">🎂 {{ c.birth_date }}</small>
              <button class="btn-edit-inline" @click="editingId = c.id; newNameValue = c.name">✏️</button>
            </div>
          </td>
          <td class="balance-cell">€{{ c.balance.toFixed(2) }}</td>
          <td class="text-right actions-cell">
            <button class="btn-secondary" @click="activeAdjustId = c.id">Adjust</button>
            <button class="btn-icon-delete" @click="deleteChild(c.id)">🗑️</button>
          </td>
        </tr>
        </tbody>
      </table>
    </div>

    <div class="tile wish-admin-tile">
      <div class="tile-header">
        <h3>✨ Manage Wish Lists</h3>
        <select v-model="selectedChildForWishes" class="child-select">
          <option v-for="c in children" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>

      <div class="add-wish-form">
        <input v-model="newWish.item_name" placeholder="Item name (e.g. LEGO)">
        <div class="cost-input-wrapper">
          <span class="currency-prefix">€</span>
          <input v-model.number="newWish.cost" type="number" placeholder="0.00" step="0.01">
        </div>
        <button @click="addWish" class="btn-success">Add Wish</button>
      </div>

      <div class="wish-list-table">
        <div v-if="childWishes.length === 0" class="empty-text">No wishes found for this child.</div>
        <table v-else>
          <thead>
          <tr>
            <th>Item</th>
            <th>Cost</th>
            <th class="text-right">Actions</th>
          </tr>
          </thead>
          <tbody>
          <tr v-for="w in childWishes" :key="w.id">
            <td v-if="editingWishId === w.id">
              <input v-model="editWishName" class="small-input">
            </td>
            <td v-else>{{ w.item_name }}</td>

            <td v-if="editingWishId === w.id">
              <input v-model.number="editWishCost" type="number" step="0.01" class="small-input" style="width: 70px;">
            </td>
            <td v-else>€{{ w.cost.toFixed(2) }}</td>

            <td class="text-right">
              <div v-if="editingWishId === w.id">
                <button @click="handleUpdateWish(w.id)" class="btn-mini-save">Save</button>
                <button @click="editingWishId = null" class="btn-mini-cancel" style="background: #ccc;">X</button>
              </div>
              <div v-else>
                <button @click="editingWishId = w.id; editWishName = w.item_name; editWishCost = w.cost"
                        class="btn-edit-inline">✏️
                </button>
                <button @click="buyWish(w)" class="btn-mini-buy">💰 Buy</button>
                <button @click="deleteWish(w.id)" class="btn-mini-cancel">Remove</button>
              </div>
            </td>
          </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Transition name="fade">
      <div v-if="activeAdjustId" class="modal-overlay" @click.self="closeModal">
        <div class="modal-card">
          <div class="modal-header">
            <h3>Modify Balance</h3>
            <p>Adjusting <strong>{{ currentChild?.name }}</strong></p>
          </div>
          <div class="modal-body">
            <div class="input-field"><label>Amount (€)</label><input type="number" v-model="adjustAmount" step="0.01">
            </div>
            <div class="input-field"><label>Reason</label><input v-model="adjustReason" placeholder="Reason..."></div>
            <div class="input-field">
              <label>Category</label>
              <select v-model="adjustCategory">
                <option>Reward</option>
                <option>Fine</option>
                <option>Gift</option>
                <option>Correction</option>
              </select>
            </div>
            <div class="preview-box" v-if="adjustAmount !== 0">
              <div class="preview-item"><span>Current:</span><span>€{{ currentChild?.balance.toFixed(2) }}</span></div>
              <div class="preview-item highlight"><span>If Added:</span><span
                  class="pos">€{{ previewBalance.ifAdded.toFixed(2) }}</span></div>
              <div class="preview-item highlight"><span>If Subtracted:</span><span
                  class="neg">€{{ previewBalance.ifSubtracted.toFixed(2) }}</span></div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-outline" @click="closeModal">Cancel</button>
            <div class="action-group">
              <button class="btn-danger" @click="handleAdjustment('remove')">Subtract</button>
              <button class="btn-success" @click="handleAdjustment('add')">Add Money</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.admin-view {
  max-width: 900px;
  margin: 0 auto;
  padding-bottom: 50px;
}

.tile {
  background: white;
  border-radius: 16px;
  padding: 25px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
  margin-bottom: 25px;
}

.tile-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

/* Unified Input Sizing */
input, select, .cost-input-wrapper {
  height: 45px;
  box-sizing: border-box;
}

.input-group, .add-wish-form {
  display: flex;
  gap: 12px;
  align-items: center;
}

.display-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.edit-group {
  display: flex;
  gap: 5px;
}

.small-input {
  width: 120px;
  height: 35px;
}

.add-wish-form {
  background: #f8f9fa;
  padding: 15px;
  border-radius: 12px;
  margin-bottom: 20px;
}

.add-wish-form input[type="text"] {
  flex: 2;
}

.cost-input-wrapper {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}

input {
  padding: 0 15px;
  border: 2px solid #f1f2f6;
  border-radius: 10px;
  outline: none;
  font-size: 1rem;
}

.cost-input-wrapper input {
  padding-left: 30px;
  width: 100%;
}

.currency-prefix {
  position: absolute;
  left: 12px;
  font-weight: bold;
  color: #747d8c;
}

/* Tables */
table {
  width: 100%;
  border-collapse: collapse;
}

th {
  text-align: left;
  font-size: 0.75rem;
  color: #a0a0a0;
  text-transform: uppercase;
  padding: 10px;
}

td {
  padding: 12px 10px;
  border-bottom: 1px solid #f9f9f9;
}

.text-right {
  text-align: right;
}

.actions-cell {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  align-items: center;
}

/* Buttons */
button {
  height: 45px;
  padding: 0 20px;
  border-radius: 10px;
  font-weight: bold;
  cursor: pointer;
  border: none;
  transition: transform 0.1s;
}

button:active {
  transform: scale(0.98);
}

.btn-success {
  background: #2ed573;
  color: white;
}

.btn-danger {
  background: #ff4757;
  color: white;
}

.btn-mini-buy {
  background: #4a90e2;
  color: white;
  height: 32px;
  padding: 0 12px;
  font-size: 0.85rem;
}

.btn-mini-cancel {
  background: #ff4757;
  color: white;
  height: 32px;
  padding: 0 12px;
  font-size: 0.85rem;
}

.btn-secondary {
  background: #f1f2f6;
  height: 38px;
}

.btn-edit-inline {
  background: none;
  height: auto;
  padding: 5px;
  font-size: 1rem;
}

.btn-mini-save {
  height: 35px;
  padding: 0 10px;
  background: #2ed573;
  color: white;
}

.btn-icon-delete {
  background: none;
  height: auto;
  padding: 5px;
  font-size: 1.2rem;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-card {
  background: white;
  width: 400px;
  border-radius: 20px;
  padding: 25px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
}

.input-field {
  margin-bottom: 15px;
}

.input-field label {
  display: block;
  font-size: 0.8rem;
  margin-bottom: 5px;
  color: #747d8c;
  font-weight: bold;
}

.input-field input {
  width: 100%;
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
