<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const portfolio = ref({ shares: [], etfs: [], timestamp: '' })
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8005/v1';

const fetchPortfolio = async () => {
  try {
    const res = await axios.get(`${API_BASE}/investments/dashboard-summary`)
    portfolio.value = res.data
  } catch (e) {
    console.error("Error fetching portfolio:", e)
  }
}

const formatCurrency = (amount) => {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

const formatPercentage = (pct) => {
  return pct.toFixed(2) + '%'
}

onMounted(fetchPortfolio)
</script>

<template>
  <div class="dashboard">
    <h2>Portfolio Overview</h2>
    <p class="timestamp">Last updated: {{ new Date(portfolio.timestamp).toLocaleString() }}</p>

    <div class="sections">
      <div class="section">
        <h3>Employee Shares</h3>
        <div v-if="portfolio.shares.length === 0" class="empty">No shares data available.</div>
        <div v-else class="table-container">
          <table class="portfolio-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Available Shares</th>
                <th>Pending Shares</th>
                <th>Live Price</th>
                <th>Available Value</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="share in portfolio.shares" :key="share.ticker">
                <td>{{ share.ticker }}</td>
                <td>{{ share.available_shares.toFixed(4) }}</td>
                <td>{{ share.pending_shares.toFixed(4) }}</td>
                <td>{{ formatCurrency(share.live_price) }}</td>
                <td>{{ formatCurrency(share.available_value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="section">
        <h3>ETF Investments</h3>
        <div v-if="portfolio.etfs.length === 0" class="empty">No ETF data available.</div>
        <div v-else class="table-container">
          <table class="portfolio-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Total Shares</th>
                <th>Total Invested</th>
                <th>Live Price</th>
                <th>Current Value</th>
                <th>ROI ($)</th>
                <th>ROI (%)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="etf in portfolio.etfs" :key="etf.ticker">
                <td>{{ etf.ticker }}</td>
                <td>{{ etf.total_shares.toFixed(6) }}</td>
                <td>{{ formatCurrency(etf.total_invested) }}</td>
                <td>{{ formatCurrency(etf.live_price) }}</td>
                <td>{{ formatCurrency(etf.current_value) }}</td>
                <td :class="etf.roi_fiat >= 0 ? 'positive' : 'negative'">{{ formatCurrency(etf.roi_fiat) }}</td>
                <td :class="etf.roi_percentage >= 0 ? 'positive' : 'negative'">{{ formatPercentage(etf.roi_percentage) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 1200px;
  margin: 0 auto;
}

.timestamp {
  color: #666;
  font-size: 0.9rem;
  margin-bottom: 20px;
}

.sections {
  display: grid;
  gap: 30px;
}

.section {
  background: white;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}

.section h3 {
  margin-top: 0;
  color: #2d3436;
}

.empty {
  text-align: center;
  color: #999;
  padding: 40px;
  font-style: italic;
}

.table-container {
  overflow-x: auto;
}

.portfolio-table {
  width: 100%;
  border-collapse: collapse;
}

.portfolio-table th,
.portfolio-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.portfolio-table th {
  background: #f8f9fa;
  font-weight: bold;
  color: #2d3436;
}

.positive {
  color: #2ed573;
}

.negative {
  color: #ff4757;
}
</style>
