<script setup>
import {ref, onMounted, watch, nextTick} from 'vue'
import axios from 'axios'
import Chart from 'chart.js/auto'

const portfolio = ref({shares: [], etfs: [], vesting_timeline: [], timestamp: ''})
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8005/v1';

// Chart Refs
const chartTotal = ref(null)
const chartAvailable = ref(null)
const chartPending = ref(null)
const chartTimeline = ref(null)

let totalChartInstance = null
let availableChartInstance = null
let pendingChartInstance = null
let timelineChartInstance = null

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

const renderCharts = async () => {
  await nextTick() // Ensure DOM is ready
  if (!portfolio.value.shares || portfolio.value.shares.length === 0) return;

  const labels = portfolio.value.shares.map(s => s.ticker)
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {legend: {position: 'bottom'}}
  }

  // 1. Total Distribution (Pie)
  if (totalChartInstance) totalChartInstance.destroy()
  totalChartInstance = new Chart(chartTotal.value, {
    type: 'pie',
    data: {
      labels,
      datasets: [{
        data: portfolio.value.shares.map(s => s.total_value),
        backgroundColor: ['#4a90e2', '#50e3c2', '#f5a623', '#d0021b']
      }]
    },
    options: commonOptions
  })

  // 2. Vested Value (Bar)
  if (availableChartInstance) availableChartInstance.destroy()
  availableChartInstance = new Chart(chartAvailable.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Vested Value ($)',
        data: portfolio.value.shares.map(s => s.available_value),
        backgroundColor: '#27ae60'
      }]
    },
    options: commonOptions
  })

  // 3. Unvested Value (Bar)
  if (pendingChartInstance) pendingChartInstance.destroy()
  pendingChartInstance = new Chart(chartPending.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Unvested Value ($)',
        data: portfolio.value.shares.map(s => s.pending_value),
        backgroundColor: '#f1c40f'
      }]
    },
    options: commonOptions
  })

  // 4. Vesting Timeline (Staircase Line Plot)
  if (portfolio.value.vesting_timeline && portfolio.value.vesting_timeline.length > 0) {
    if (timelineChartInstance) timelineChartInstance.destroy()
    timelineChartInstance = new Chart(chartTimeline.value, {
      type: 'line',
      data: {
        labels: portfolio.value.vesting_timeline.map(t => t.date),
        datasets: [{
          label: 'Portfolio Value Projection',
          data: portfolio.value.vesting_timeline.map(t => t.value),
          borderColor: '#4a90e2',
          backgroundColor: 'rgba(74, 144, 226, 0.1)',
          fill: true,
          tension: 0.1,        // Slight curve for a "simple line" feel
          pointRadius: 6,      // Larger points to make the 3-4 data points stand out
          pointHoverRadius: 8,
          pointBackgroundColor: '#4a90e2'
        }]
      },
      options: {
        ...commonOptions,
        scales: {
          x: {
            ticks: {
              autoSkip: true,   // This hides intermediate dates if they get crowded
              maxTicksLimit: 5  // Limits the X-axis to roughly 4-5 labels
            }
          },
          y: {
            beginAtZero: true,
            ticks: {
              callback: (value) => '$' + value.toLocaleString()
            }
          }
        },
        plugins: {
          tooltip: {
            mode: 'index',
            intersect: false
          }
        }
      }
    })
  }
}

watch(() => portfolio.value, () => renderCharts(), {deep: true})
onMounted(fetchPortfolio)
</script>

<template>
  <div class="dashboard">
    <div class="header">
      <h2>Portfolio Overview</h2>
      <p class="timestamp" v-if="portfolio.timestamp">
        Last updated: {{ new Date(portfolio.timestamp).toLocaleString() }}
      </p>
    </div>

    <div class="sections">
      <div class="section highlight" v-if="portfolio.vesting_timeline?.length > 0">
        <h3>Projected Vesting Timeline</h3>
        <div class="canvas-wrapper timeline">
          <canvas ref="chartTimeline"></canvas>
        </div>
      </div>

      <div class="section">
        <h3>Employee Shares Status</h3>
        <div class="table-container">
          <table class="portfolio-table">
            <thead>
            <tr>
              <th>Ticker</th>
              <th>Vested</th>
              <th>Pending</th>
              <th>Live Price</th>
              <th>Vested Value</th>
              <th>Total Potential</th>
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
        <h3>Asset Allocation</h3>
        <div class="charts-grid">
          <div class="chart-box">
            <h4>Share Distribution</h4>
            <div class="canvas-wrapper">
              <canvas ref="chartTotal"></canvas>
            </div>
          </div>
          <div class="chart-box">
            <h4>Value Vested</h4>
            <div class="canvas-wrapper">
              <canvas ref="chartAvailable"></canvas>
            </div>
          </div>
          <div class="chart-box">
            <h4>Value Pending</h4>
            <div class="canvas-wrapper">
              <canvas ref="chartPending"></canvas>
            </div>
          </div>
        </div>
      </div>

      <div class="section" v-if="portfolio.etfs.length > 0">
        <h3>Other Investments</h3>
        <div class="table-container">
          <table class="portfolio-table">
            <thead>
            <tr>
              <th>Ticker</th>
              <th>Units</th>
              <th>Invested</th>
              <th>Current Value</th>
              <th>Return</th>
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
.dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 20px 80px 20px;
  font-family: sans-serif;
}

.header {
  margin-bottom: 30px;
}

.timestamp {
  color: #666;
  font-size: 0.85rem;
  margin-top: 5px;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 30px;
}

.section {
  background: white;
  padding: 24px;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.section.highlight {
  border-top: 4px solid #4a90e2;
}

.section h3 {
  margin: 0 0 20px 0;
  font-size: 1.2rem;
  color: #333;
  border-bottom: 1px solid #eee;
  padding-bottom: 10px;
}

/* Table Styling */
.table-container {
  width: 100%;
  overflow-x: auto;
  border-radius: 8px;
}

.portfolio-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 700px;
}

.portfolio-table th {
  background: #f8f9fa;
  padding: 14px;
  text-align: left;
  font-size: 0.9rem;
  color: #555;
}

.portfolio-table td {
  padding: 14px;
  border-bottom: 1px solid #f0f0f0;
  font-size: 0.95rem;
}

/* Chart Layouts */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}

.chart-box {
  background: #fafafa;
  padding: 15px;
  border-radius: 10px;
  border: 1px solid #eee;
}

.chart-box h4 {
  margin: 0 0 15px 0;
  font-size: 0.9rem;
  color: #666;
}

.canvas-wrapper {
  position: relative;
  height: 260px;
  width: 100%;
}

.canvas-wrapper.timeline {
  height: 350px;
}

/* Helpers */
.positive {
  color: #27ae60;
  font-weight: 600;
}

.negative {
  color: #e74c3c;
  font-weight: 600;
}

@media (max-width: 768px) {
  .section {
    padding: 15px;
  }

  .canvas-wrapper.timeline {
    height: 250px;
  }
}
</style>
