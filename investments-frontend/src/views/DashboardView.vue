<script setup>
import {ref, onMounted, watch, nextTick} from 'vue'
import axios from 'axios'
import Chart from 'chart.js/auto'

const portfolio = ref({shares: [], etfs: [], timestamp: ''})
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8005/v1';

// Chart Refs
const chartTotal = ref(null)
const chartAvailable = ref(null)
const chartPending = ref(null)

let totalChartInstance = null
let availableChartInstance = null
let pendingChartInstance = null

const fetchPortfolio = async () => {
  try {
    const res = await axios.get(`${API_BASE}/investments/dashboard-summary`)
    portfolio.value = res.data
  } catch (e) {
    console.error("Error fetching portfolio:", e)
  }
}

const formatCurrency = (amount) => {
  return new Intl.NumberFormat('en-US', {style: 'currency', currency: 'USD'}).format(amount || 0)
}

const formatPercentage = (pct) => {
  return (pct || 0).toFixed(2) + '%'
}

// Chart Generation Logic
const renderCharts = () => {
  if (!portfolio.value.shares || portfolio.value.shares.length === 0) return;

  const labels = portfolio.value.shares.map(s => s.ticker);

  // These must match format_shares in investments.py exactly
  const totalValueData = portfolio.value.shares.map(s => s.total_value);
  const availableValueData = portfolio.value.shares.map(s => s.available_value);
  const pendingValueData = portfolio.value.shares.map(s => s.pending_value);

  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom' } }
  };

  // Total Chart
  if (totalChartInstance) totalChartInstance.destroy()
  totalChartInstance = new Chart(chartTotal.value, {
    type: 'pie',
    data: {
      labels,
      datasets: [{ data: totalValueData, backgroundColor: ['#4a90e2', '#50e3c2', '#f5a623', '#d0021b'] }]
    },
    options: commonOptions
  })

  // Available Chart
  if (availableChartInstance) availableChartInstance.destroy()
  availableChartInstance = new Chart(chartAvailable.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Vested Value ($)', data: availableValueData, backgroundColor: '#27ae60' }]
    },
    options: commonOptions
  })

  // Pending Chart
  if (pendingChartInstance) pendingChartInstance.destroy()
  pendingChartInstance = new Chart(chartPending.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Unvested Value ($)', data: pendingValueData, backgroundColor: '#f1c40f' }]
    },
    options: commonOptions
  })
}

const renderTimelineChart = () => {
  const labels = portfolio.value.vesting_timeline.map(item => item.date);
  const data = portfolio.value.vesting_timeline.map(item => {
    // Multiply cumulative shares by the current price of the first ticker (e.g., Airbus)
    const price = portfolio.value.shares[0]?.live_price || 0;
    return item.shares_at_date * price;
  });

  // Create Line Chart with 'stepped: true'
  new Chart(chartTimeline.value, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Projected Vested Value',
        data: data,
        stepped: true, // This creates the staircase look
        borderColor: '#4a90e2',
        fill: true,
        backgroundColor: 'rgba(74, 144, 226, 0.1)'
      }]
    }
  });
}

watch(() => portfolio.value.shares, async () => {
  await nextTick()
  renderCharts()
}, {deep: true})

onMounted(fetchPortfolio)
</script>

<template>
  <div class="dashboard">
    <h2>Portfolio Overview</h2>
    <p class="timestamp" v-if="portfolio.timestamp">
      Last updated: {{ new Date(portfolio.timestamp).toLocaleString() }}
    </p>

    <div class="sections">
      <div class="section">
        <h3>Employee Shares</h3>
        <div v-if="portfolio.shares.length === 0" class="empty">No shares data available.</div>
        <div v-else class="table-container">
          <table class="portfolio-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Vested Shares</th>
                <th>Pending Shares</th>
                <th>Live Price</th>
                <th>Current Vested Value</th>
                <th>Projected Total Value</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="share in portfolio.shares" :key="share.ticker">
                <td><strong>{{ share.ticker }}</strong></td>
                <td>{{ share.available_shares.toFixed(2) }}</td>
                <td>{{ share.pending_shares.toFixed(2) }}</td>
                <td>{{ formatCurrency(share.live_price) }}</td>
                <td>{{ formatCurrency(share.available_value) }}</td>
                <td class="positive">{{ formatCurrency(share.total_value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="section" v-if="portfolio.shares.length > 0">
        <h3>Portfolio Visuals</h3>
        <div class="charts-grid">
          <div class="chart-box">
            <h4>Total Value Distribution</h4>
            <div class="canvas-wrapper"><canvas ref="chartTotal"></canvas></div>
          </div>
          <div class="chart-box">
            <h4>Vested (Available)</h4>
            <div class="canvas-wrapper"><canvas ref="chartAvailable"></canvas></div>
          </div>
          <div class="chart-box">
            <h4>Unvested (Pending)</h4>
            <div class="canvas-wrapper"><canvas ref="chartPending"></canvas></div>
          </div>
        </div>
      </div>

      <div class="section">
        <h3>ETFs & Manual Investments</h3>
        <div v-if="portfolio.etfs.length === 0" class="empty">No ETF data available.</div>
        <div v-else class="table-container">
          <table class="portfolio-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Shares</th>
                <th>Invested</th>
                <th>Current Value</th>
                <th>Gain/Loss</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="etf in portfolio.etfs" :key="etf.ticker">
                <td>{{ etf.ticker }}</td>
                <td>{{ etf.total_shares.toFixed(4) }}</td>
                <td>{{ formatCurrency(etf.total_invested) }}</td>
                <td>{{ formatCurrency(etf.current_value) }}</td>
                <td :class="etf.roi_fiat >= 0 ? 'positive' : 'negative'">
                  {{ formatCurrency(etf.roi_fiat) }} ({{ formatPercentage(etf.roi_percentage) }})
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1200px; margin: 0 auto; padding: 20px; padding-bottom: 60px; }
.timestamp { color: #666; font-size: 0.9rem; margin-bottom: 20px; }
.sections { display: grid; gap: 30px; }
.section { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.section h3 { margin-top: 0; margin-bottom: 20px; color: #2d3436; border-bottom: 2px solid #f0f2f5; padding-bottom: 10px; }

/* Table Responsiveness */
.table-container { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.portfolio-table { width: 100%; border-collapse: collapse; min-width: 600px; }
.portfolio-table th, .portfolio-table td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
.portfolio-table th { background-color: #f8f9fa; font-weight: 600; color: #2d3436; }

/* Mobile Improvements for Charts */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}
.chart-box { background: #fdfdfd; padding: 15px; border-radius: 8px; border: 1px solid #eee; text-align: center; }
.canvas-wrapper { position: relative; height: 250px; width: 100%; }

.positive { color: #27ae60; font-weight: bold; }
.negative { color: #e74c3c; font-weight: bold; }
.empty { text-align: center; color: #999; padding: 40px; }

@media (max-width: 600px) {
  .dashboard { padding: 10px; }
  .section { padding: 15px; }
  .portfolio-table th, .portfolio-table td { padding: 8px; font-size: 0.8rem; }
}
</style>
