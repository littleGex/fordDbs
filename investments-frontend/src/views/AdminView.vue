<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const schedules = ref([])
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8005/v1';

// Forms
const shareForm = ref({ ticker: '', num_shares: 0, vest_date: '', purchase_price: 0 })
const etfForm = ref({ ticker: '', fiat_amount: 0, shares_acquired: 0, transaction_type: 'buy' })
const scheduleForm = ref({ ticker: '', fiat_amount: 0, execution_day: 1 })
const sharesCsv = ref('')
const etfCsv = ref('')

const fetchSchedules = async () => {
  try {
    const res = await axios.get(`${API_BASE}/investments/etf/schedules`)
    schedules.value = res.data
  } catch (e) {
    console.error("Error fetching schedules:", e)
  }
}

const addShare = async () => {
  try {
    await axios.post(`${API_BASE}/investments/shares/add`, null, {
      params: shareForm.value
    })
    alert('Share added successfully!')
    shareForm.value = { ticker: '', num_shares: 0, vest_date: '', purchase_price: 0 }
  } catch (e) {
    alert('Error adding share: ' + e.response?.data?.detail || e.message)
  }
}

const addEtfTransaction = async () => {
  try {
    await axios.post(`${API_BASE}/investments/etf/transaction`, null, {
      params: etfForm.value
    })
    alert('ETF transaction recorded!')
    etfForm.value = { ticker: '', fiat_amount: 0, shares_acquired: 0, transaction_type: 'buy' }
  } catch (e) {
    alert('Error recording transaction: ' + e.response?.data?.detail || e.message)
  }
}

const createSchedule = async () => {
  try {
    await axios.post(`${API_BASE}/investments/etf/schedule`, null, {
      params: scheduleForm.value
    })
    alert('Schedule created!')
    scheduleForm.value = { ticker: '', fiat_amount: 0, execution_day: 1 }
    fetchSchedules()
  } catch (e) {
    alert('Error creating schedule: ' + e.response?.data?.detail || e.message)
  }
}

const deleteSchedule = async (id) => {
  const password = prompt('Enter admin password to delete:')
  if (!password) return

  try {
    await axios.delete(`${API_BASE}/investments/etf/schedule/${id}`, {
      params: { password }
    })
    alert('Schedule deleted!')
    fetchSchedules()
  } catch (e) {
    alert('Error deleting schedule: ' + e.response?.data?.detail || e.message)
  }
}

const importShares = async () => {
  const password = prompt('Enter admin password to import shares:')
  if (!password) return

  try {
    const lines = sharesCsv.value.split('\n').filter(line => line.trim() !== '')
    for (const line of lines) {
      const [ticker, num_shares, vest_date, purchase_price] = line.split(',').map(item => item.trim())
      await axios.post(`${API_BASE}/investments/shares/add`, null, {
        params: { ticker, num_shares: Number(num_shares), vest_date, purchase_price: Number(purchase_price) }
      })
    }
    alert('Shares imported successfully!')
    sharesCsv.value = ''
    fetchSchedules()
  } catch (e) {
    alert('Error importing shares: ' + e.response?.data?.detail || e.message)
  }
}

const importEtfTransactions = async () => {
  const password = prompt('Enter admin password to import ETF transactions:')
  if (!password) return

  try {
    const lines = etfCsv.value.split('\n').filter(line => line.trim() !== '')
    for (const line of lines) {
      const [ticker, fiat_amount, shares_acquired, transaction_date, fees, transaction_type] = line.split(',').map(item => item.trim())
      await axios.post(`${API_BASE}/investments/etf/transaction`, null, {
        params: { ticker, fiat_amount: Number(fiat_amount), shares_acquired: Number(shares_acquired), transaction_date, fees: Number(fees), transaction_type: transaction_type || 'buy' }
      })
    }
    alert('ETF transactions imported successfully!')
    etfCsv.value = ''
    fetchSchedules()
  } catch (e) {
    alert('Error importing ETF transactions: ' + e.response?.data?.detail || e.message)
  }
}

const uploadSharesCsv = async () => {
  try {
    await axios.post(`${API_BASE}/investments/shares/bulk-add`, {
      csv_data: sharesCsv.value
    });
    alert('Bulk shares added successfully!');
    sharesCsv.value = '';
  } catch (e) {
    alert('Failed to upload CSV: ' + (e.response?.data?.detail || e.message));
  }
}

onMounted(fetchSchedules)
</script>

<template>
  <div class="admin">
    <h2>Admin Panel</h2>

    <div class="forms-grid">
      <div class="form-section">
        <h3>Add Employee Share</h3>
        <form @submit.prevent="addShare">
          <input v-model="shareForm.ticker" placeholder="Ticker Symbol" required>
          <input v-model.number="shareForm.num_shares" type="number" step="0.0001" placeholder="Number of Shares" required>
          <input v-model="shareForm.vest_date" type="date" placeholder="Vest Date" required>
          <input v-model.number="shareForm.purchase_price" type="number" step="0.01" placeholder="Purchase Price (optional)">
          <button type="submit">Add Share</button>
        </form>
      </div>

      <div class="form-section">
        <h3>Record ETF Transaction</h3>
        <form @submit.prevent="addEtfTransaction">
          <input v-model="etfForm.ticker" placeholder="Ticker Symbol" required>
          <input v-model.number="etfForm.fiat_amount" type="number" step="0.01" placeholder="Fiat Amount Invested" required>
          <input v-model.number="etfForm.shares_acquired" type="number" step="0.000001" placeholder="Shares Acquired" required>
          <select v-model="etfForm.transaction_type">
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
          <button type="submit">Record Transaction</button>
        </form>
      </div>

      <div class="form-section">
        <h3>Create ETF Purchase Schedule</h3>
        <form @submit.prevent="createSchedule">
          <input v-model="scheduleForm.ticker" placeholder="Ticker Symbol" required>
          <input v-model.number="scheduleForm.fiat_amount" type="number" step="0.01" placeholder="Fiat Amount" required>
          <input v-model.number="scheduleForm.execution_day" type="number" min="1" max="28" placeholder="Execution Day (1-28)" required>
          <button type="submit">Create Schedule</button>
        </form>
      </div>

      <div class="form-section">
        <h3>Bulk Import Shares (CSV)</h3>
        <form @submit.prevent="importShares">
          <textarea v-model="sharesCsv" placeholder="ticker,num_shares,vest_date,purchase_price&#10;AAPL,100,2024-01-01,150.00&#10;GOOGL,50,2024-02-01,2800.00" rows="5"></textarea>
          <button @click="uploadSharesCsv">Import Shares</button>
        </form>
      </div>

      <div class="form-section">
        <h3>Bulk Import ETF Transactions (CSV)</h3>
        <form @submit.prevent="importEtfTransactions">
          <textarea v-model="etfCsv" placeholder="ticker,fiat_amount,shares_acquired,transaction_date,fees,transaction_type&#10;VTI,1000.00,10.5,2024-01-01,5.00,buy&#10;VXUS,500.00,7.2,2024-02-01,2.50,sell" rows="5"></textarea>
          <button type="submit">Import ETF Transactions</button>
        </form>
      </div>
    </div>

    <div class="schedules-section">
      <h3>ETF Purchase Schedules</h3>
      <div v-if="schedules.length === 0" class="empty">No schedules found.</div>
      <div v-else class="schedule-list">
        <div v-for="schedule in schedules" :key="schedule.schedule_id" class="schedule-item">
          <div class="schedule-info">
            <strong>{{ schedule.ticker_symbol }}</strong> - {{ schedule.fiat_amount }} on day {{ schedule.execution_day }}
            <span v-if="!schedule.is_active" class="inactive">(Inactive)</span>
          </div>
          <button @click="deleteSchedule(schedule.schedule_id)" class="btn-delete">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin {
  max-width: 1000px;
  margin: 0 auto;
}

.forms-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-bottom: 40px;
}

.form-section {
  background: white;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.form-section h3 {
  margin-top: 0;
  color: #2d3436;
}

.form-section form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.form-section input, .form-section textarea {
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.form-section button {
  padding: 10px;
  background: #4a90e2;
  color: white;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-weight: bold;
}

.schedules-section {
  background: white;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.schedule-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  border: 1px solid #eee;
  border-radius: 5px;
}

.btn-delete {
  background: #ff4757;
  color: white;
  border: none;
  padding: 5px 10px;
  border-radius: 5px;
  cursor: pointer;
}

.inactive {
  color: #999;
  font-style: italic;
}

.empty {
  text-align: center;
  color: #999;
  padding: 20px;
  font-style: italic;
}
</style>
