<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const schedules = ref([])

// Forms
const shareForm = ref({ ticker: '', num_shares: 0, vest_date: '', purchase_price: 0 })
const etfForm = ref({ ticker: '', fiat_amount: 0, shares_acquired: 0, transaction_type: 'buy' })
const scheduleForm = ref({ ticker: '', isin: '', fiat_amount: 0, execution_day: 1 })
const instruments = ref([])
const instrumentForm = ref({ isin: '', name: '' })
// Per-ISIN inputs for "Set ticker" and "Link existing ticker"
const tickerInputs = ref({})
const linkInputs = ref({})
const busy = ref('')

const errorText = (e) =>
  e.response?.data?.detail?.message || e.response?.data?.detail || e.message
const sharesCsv = ref('')
const etfCsv = ref('')

// Trade Republic export import (#45)
const TR_MAX_BYTES = 5 * 1024 * 1024
const trFile = ref(null)
const trBusy = ref('')
const trResult = ref(null)
const trError = ref('')

const fetchSchedules = async () => {
  try {
    const res = await api.get(`/investments/etf/schedules`)
    schedules.value = res.data
  } catch (e) {
    console.error("Error fetching schedules:", e)
  }
}

const addShare = async () => {
  try {
    await api.post(`/investments/shares/add`, null, {
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
    await api.post(`/investments/etf/transaction`, null, {
      params: etfForm.value
    })
    alert('ETF transaction recorded!')
    etfForm.value = { ticker: '', fiat_amount: 0, shares_acquired: 0, transaction_type: 'buy' }
  } catch (e) {
    alert('Error recording transaction: ' + e.response?.data?.detail || e.message)
  }
}

// Trade Republic is the source of truth for funds whose fills are
// imported: an app schedule for them would count each month twice.
const importedInstrumentFor = (isin, ticker) => instruments.value.find(inst =>
  inst.imported > 0 && (isin
    ? inst.isin === isin.toUpperCase()
    : inst.yahoo_ticker && inst.yahoo_ticker === ticker.trim().toUpperCase()))

const createSchedule = async () => {
  const { ticker, isin, fiat_amount, execution_day } = scheduleForm.value
  if (importedInstrumentFor(isin.trim(), ticker) &&
      !confirm('Trade Republic fills for this fund are imported; an app schedule would count them twice. Create anyway?')) return
  const params = { amount: fiat_amount, day: execution_day }
  if (isin.trim()) params.isin = isin.trim()
  else params.ticker = ticker
  try {
    await api.post(`/investments/etf/schedule`, null, { params })
    alert('Schedule created!')
    scheduleForm.value = { ticker: '', isin: '', fiat_amount: 0, execution_day: 1 }
    fetchSchedules()
    fetchInstruments()
  } catch (e) {
    alert('Error creating schedule: ' + errorText(e))
  }
}

// --- Instruments (ISIN -> Yahoo ticker) ---

const fetchInstruments = async () => {
  try {
    const res = await api.get(`/investments/instruments`)
    instruments.value = res.data
  } catch (e) {
    console.error('Error fetching instruments:', e)
  }
}

const withBusy = async (key, fn) => {
  busy.value = key
  try {
    await fn()
  } finally {
    busy.value = ''
  }
}

const addInstrument = () => withBusy('add', async () => {
  try {
    const { data } = await api.post(`/investments/instruments`, {
      isin: instrumentForm.value.isin,
      name: instrumentForm.value.name || null
    })
    instrumentForm.value = { isin: '', name: '' }
    await fetchInstruments()
    if (data.status === 'unresolved') {
      alert(`${data.isin} has no ticker yet: ${data.resolution_note}`)
    }
  } catch (e) {
    alert('Error adding ISIN: ' + errorText(e))
  }
})

const reResolve = (inst) => withBusy(inst.isin, async () => {
  try {
    await api.post(`/investments/instruments/${inst.isin}/resolve`)
    await fetchInstruments()
  } catch (e) {
    alert('Error looking up ticker: ' + errorText(e))
  }
})

const setTicker = (inst) => withBusy(inst.isin, async () => {
  const yahoo_ticker = (tickerInputs.value[inst.isin] || '').trim()
  if (!yahoo_ticker) return
  const url = `/investments/instruments/${inst.isin}/ticker`
  try {
    await api.put(url, { yahoo_ticker })
  } catch (e) {
    const d = e.response?.data?.detail
    if (e.response?.status !== 409 || !d?.reference_date) {
      alert('Error setting ticker: ' + errorText(e))
      return
    }
    const ok = confirm(`${d.message}\n\nFill on ${d.reference_date}: ${d.reference_price} EUR\n` +
      `${yahoo_ticker} close: ${d.close} EUR\n\nUse ${yahoo_ticker} anyway?`)
    if (!ok) return
    try {
      await api.put(url, { yahoo_ticker, confirm: true })
    } catch (e2) {
      alert('Error setting ticker: ' + errorText(e2))
      return
    }
  }
  tickerInputs.value[inst.isin] = ''
  await Promise.all([fetchInstruments(), fetchSchedules()])
})

const unlinkInstrument = (inst) => withBusy(inst.isin, async () => {
  const ok = confirm(`Unlink ${inst.transactions} transaction(s) and ${inst.schedules} schedule(s) from ${inst.isin}?\n\n` +
    `They keep the ticker ${inst.yahoo_ticker || '(unchanged)'}. To correct a wrong link, then link that ticker to the right ISIN.`)
  if (!ok) return
  try {
    const { data } = await api.post(`/investments/instruments/${inst.isin}/unlink`)
    alert(`Unlinked ${data.transactions} transaction(s) and ${data.schedules} schedule(s).`)
    await Promise.all([fetchInstruments(), fetchSchedules()])
  } catch (e) {
    alert('Error unlinking: ' + errorText(e))
  }
})

const linkTicker = (inst) => withBusy(inst.isin, async () => {
  const ticker_symbol = (linkInputs.value[inst.isin] || '').trim()
  if (!ticker_symbol) return
  try {
    const { data } = await api.post(`/investments/instruments/${inst.isin}/link`, { ticker_symbol })
    linkInputs.value[inst.isin] = ''
    let msg = `Linked ${data.transactions} transaction(s) and ${data.schedules} schedule(s).`
    if (data.conflicts) msg += ` ${data.conflicts} row(s) already belong to another ISIN and were left alone.`
    alert(msg)
    await Promise.all([fetchInstruments(), fetchSchedules()])
  } catch (e) {
    alert('Error linking ticker: ' + errorText(e))
  }
})

const deleteSchedule = async (id) => {
  if (!confirm('Delete this schedule?')) return

  try {
    await api.delete(`/investments/etf/schedule/${id}`)
    alert('Schedule deleted!')
    fetchSchedules()
  } catch (e) {
    alert('Error deleting schedule: ' + e.response?.data?.detail || e.message)
  }
}

const importShares = async () => {
  try {
    const lines = sharesCsv.value.split('\n').filter(line => line.trim() !== '')
    for (const line of lines) {
      const [ticker, num_shares, vest_date, purchase_price] = line.split(',').map(item => item.trim())
      await api.post(`/investments/shares/add`, null, {
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
  try {
    const { data } = await api.post(`/investments/etf/bulk-add`, {
      csv_data: etfCsv.value
    })
    alert(`Imported ${data.imported} ETF transaction(s).`)
    etfCsv.value = ''
    fetchSchedules()
  } catch (e) {
    alert('Error importing ETF transactions (nothing was imported): ' + (e.response?.data?.detail || e.message))
  }
}

const uploadSharesCsv = async () => {
  try {
    await api.post(`/investments/shares/bulk-add`, {
      csv_data: sharesCsv.value
    });
    alert('Bulk shares added successfully!');
    sharesCsv.value = '';
  } catch (e) {
    alert('Failed to upload CSV: ' + (e.response?.data?.detail || e.message));
  }
}

const onTrFile = (event) => {
  trFile.value = event.target.files[0] || null
  trResult.value = null
  trError.value = ''
}

const runTrImport = async (dryRun) => {
  const file = trFile.value
  if (!file) return
  trResult.value = null
  trError.value = ''
  if (file.size > TR_MAX_BYTES) {
    trError.value = 'This file is larger than 5 MB; is it a Trade Republic transaction export?'
    return
  }
  trBusy.value = dryRun ? 'check' : 'import'
  try {
    const { data } = await api.post(`/investments/etf/import/trade-republic`, {
      csv_data: await file.text(),
      dry_run: dryRun
    })
    trResult.value = data
    if (!dryRun) await Promise.all([fetchInstruments(), fetchSchedules()])
  } catch (e) {
    if (!e.response) {
      // No answer (e.g. a proxy timeout): the server may still have
      // finished; a dry run shows which rows are already stored.
      trError.value = 'No answer from the server. ' + (dryRun ? 'Try again.'
        : 'The import may still have finished: press Check file, rows already imported show as skipped.')
    } else {
      trError.value = (dryRun ? 'Check failed: ' : 'Import failed, nothing was imported: ') + errorText(e)
    }
  } finally {
    trBusy.value = ''
  }
}

onMounted(() => {
  fetchSchedules()
  fetchInstruments()
})
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
          <input v-model="scheduleForm.isin" placeholder="ISIN (optional, uses its ticker)">
          <input v-model="scheduleForm.ticker" placeholder="Ticker Symbol" :required="!scheduleForm.isin.trim()" :disabled="!!scheduleForm.isin.trim()">
          <input v-model.number="scheduleForm.fiat_amount" type="number" step="0.01" placeholder="Fiat Amount" required>
          <input v-model.number="scheduleForm.execution_day" type="number" min="1" max="28" placeholder="Execution Day (1-28)" required>
          <button type="submit">Create Schedule</button>
        </form>
      </div>

      <div class="form-section">
        <h3>Bulk Import Shares (CSV)</h3>
        <form @submit.prevent="uploadSharesCsv"> <textarea v-model="sharesCsv" placeholder="ticker,num_shares,vest_date,purchase_price" rows="5"></textarea>
          <button type="submit">Import Shares</button>
        </form>
      </div>

      <div class="form-section">
        <h3>Bulk Import ETF Transactions (CSV)</h3>
        <p class="hint">First line must be the header. Dates are YYYY-MM-DD; fees and transaction_type are optional (default 0 and buy).</p>
        <form @submit.prevent="importEtfTransactions">
          <textarea v-model="etfCsv" placeholder="ticker,fiat_amount,shares_acquired,transaction_date,fees,transaction_type&#10;VTI,1000.00,10.5,2024-01-01,5.00,buy&#10;VXUS,500.00,7.2,2024-02-01,2.50,sell" rows="5"></textarea>
          <button type="submit">Import ETF Transactions</button>
        </form>
      </div>

      <div class="form-section tr-import">
        <h3>Import Trade Republic export</h3>
        <p class="hint">Trade Republic app → Profile → Transaction export. Check the file first; re-importing skips rows already imported.</p>
        <input type="file" accept=".csv,text/csv" @change="onTrFile">
        <div class="tr-buttons">
          <button type="button" :disabled="!trFile || !!trBusy" @click="runTrImport(true)">{{ trBusy === 'check' ? 'Checking…' : 'Check file' }}</button>
          <button type="button" :disabled="!trFile || !!trBusy" @click="runTrImport(false)">{{ trBusy === 'import' ? 'Importing…' : 'Import' }}</button>
        </div>
        <p v-if="trError" class="tr-error">{{ trError }}</p>
        <div v-if="trResult" class="tr-result">
          <p><strong>{{ trResult.dry_run ? 'Would import' : 'Imported' }} {{ trResult.imported }}</strong> transaction(s); {{ trResult.skipped_duplicates }} already imported.</p>
          <p v-if="Object.keys(trResult.ignored).length">Ignored: <span v-for="(n, reason) in trResult.ignored" :key="reason">{{ reason }} {{ n }}&nbsp;</span></p>
          <div v-if="trResult.unknown.length">
            <p>Not understood (not imported):</p>
            <ul><li v-for="u in trResult.unknown" :key="u.line">line {{ u.line }}: {{ u.category }} / {{ u.type }}</li></ul>
          </div>
          <div v-if="trResult.warnings.length">
            <p>Warnings:</p>
            <ul><li v-for="w in trResult.warnings" :key="w">{{ w }}</li></ul>
          </div>
          <p v-if="trResult.unresolved.length">No ticker yet for {{ trResult.unresolved.join(', ') }}: set their tickers in Instruments below.</p>
        </div>
      </div>
    </div>

    <div class="schedules-section instruments-section">
      <h3>Instruments (ISIN → Yahoo ticker)</h3>
      <p class="hint">Tickers are looked up from the ISIN and must be priced in EUR. Unresolved ISINs need a ticker set by hand.</p>
      <form class="inline-form" @submit.prevent="addInstrument">
        <input v-model="instrumentForm.isin" placeholder="ISIN, e.g. IE00B4L5Y983" required>
        <input v-model="instrumentForm.name" placeholder="Name (optional)">
        <button type="submit" :disabled="busy === 'add'">{{ busy === 'add' ? 'Looking up…' : 'Add ISIN' }}</button>
      </form>
      <div v-if="instruments.length === 0" class="empty">No instruments yet.</div>
      <div v-else class="schedule-list">
        <div v-for="inst in instruments" :key="inst.isin" class="instrument-item" :class="{ unresolved: inst.status === 'unresolved' }">
          <div class="instrument-info">
            <div>
              <strong>{{ inst.isin }}</strong>
              <span class="status" :class="inst.status">{{ inst.status }}</span>
            </div>
            <div>{{ inst.name || '—' }}</div>
            <div>Ticker: <strong>{{ inst.yahoo_ticker || 'none' }}</strong>
              <span v-if="inst.currency"> ({{ inst.currency }})</span>
              · {{ inst.transactions }} transaction(s), {{ inst.schedules }} schedule(s)
            </div>
            <div v-if="inst.resolution_note" class="note">{{ inst.resolution_note }}</div>
          </div>
          <div class="instrument-actions">
            <button v-if="inst.status !== 'override'" type="button" :disabled="busy === inst.isin" @click="reResolve(inst)">Re-resolve</button>
            <form class="inline-form" @submit.prevent="setTicker(inst)">
              <input v-model="tickerInputs[inst.isin]" placeholder="Ticker, e.g. EUNL.DE">
              <button type="submit" :disabled="busy === inst.isin">Set ticker</button>
            </form>
            <button v-if="inst.transactions || inst.schedules" type="button" class="btn-unlink" :disabled="busy === inst.isin" @click="unlinkInstrument(inst)">Unlink all</button>
            <form class="inline-form" @submit.prevent="linkTicker(inst)">
              <input v-model="linkInputs[inst.isin]" placeholder="Existing ticker to link">
              <button type="submit" :disabled="busy === inst.isin">Link</button>
            </form>
          </div>
        </div>
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

.form-section .hint {
  margin: 0 0 10px;
  font-size: 0.85em;
  color: #636e72;
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

.instruments-section {
  margin-bottom: 40px;
}

.hint {
  margin: 0 0 10px;
  font-size: 0.85em;
  color: #636e72;
}

.inline-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.inline-form input {
  flex: 1 1 160px;
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.inline-form button, .instrument-actions > button {
  padding: 6px 12px;
  border: none;
  border-radius: 5px;
  background: #0984e3;
  color: white;
  cursor: pointer;
}

.inline-form button:disabled, .instrument-actions > button:disabled {
  opacity: 0.6;
  cursor: wait;
}

.instrument-item {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: space-between;
  padding: 10px;
  border: 1px solid #eee;
  border-radius: 5px;
}

.instrument-item.unresolved {
  border-color: #fdcb6e;
  background: #fffbea;
}

.instrument-info {
  flex: 1 1 280px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.instrument-actions {
  flex: 1 1 280px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.instrument-actions > button {
  align-self: flex-start;
}

.instrument-actions > .btn-unlink {
  background: #ff4757;
}

.instrument-actions .inline-form {
  margin-bottom: 0;
}

.status {
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 0.8em;
  background: #dfe6e9;
}

.status.resolved { background: #55efc4; }
.status.override { background: #74b9ff; }
.status.unresolved { background: #fdcb6e; }

.note {
  font-size: 0.85em;
  color: #636e72;
  font-weight: normal;
}

.empty {
  text-align: center;
  color: #999;
  padding: 20px;
  font-style: italic;
}
.tr-import input[type="file"] {
  margin-bottom: 0.5rem;
}

.tr-buttons {
  display: flex;
  gap: 0.5rem;
}

.tr-error {
  color: #ff4757;
}

.tr-result ul {
  margin: 0.25rem 0 0.5rem 1.25rem;
  padding: 0;
}

.tr-result p {
  margin: 0.4rem 0;
}
</style>
