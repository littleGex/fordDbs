<script setup>
import {ref, computed, onMounted, watch, nextTick} from 'vue'
import api from '../api'
import Chart from 'chart.js/auto'

const portfolio = ref({shares: [], etfs: [], vesting_timeline: [], timestamp: ''})

// Chart Refs
const chartTotal = ref(null)
const chartAvailable = ref(null)
const chartPending = ref(null)
const chartTimeline = ref(null)

let totalChartInstance = null
let availableChartInstance = null
let pendingChartInstance = null
let timelineChartInstance = null
const chartAllocation = ref(null)
const chartInvested = ref(null)
let allocationChartInstance = null
let investedChartInstance = null

const sum = (rows, key) => rows.reduce((total, row) => total + (row[key] || 0), 0)
// Holdings still owned (a sold or liquidated fund keeps its row with 0 units)
const heldEtfs = computed(() => portfolio.value.etfs.filter(e => Math.abs(e.total_shares) > 1e-9))

// Wealth = vested employee shares + ETFs & stocks at today's prices;
// unvested shares are shown but not counted. Invested is net of sells,
// so sold and liquidated funds count in the overall return.
const totals = computed(() => {
  const vested = sum(portfolio.value.shares, 'available_value')
  const unvested = sum(portfolio.value.shares, 'pending_value')
  const etfValue = sum(portfolio.value.etfs, 'current_value')
  const invested = sum(portfolio.value.etfs, 'total_invested')
  const etfReturn = etfValue - invested
  return {
    vested, unvested, etfValue, invested, etfReturn,
    etfReturnPct: invested > 0 ? etfReturn / invested * 100 : 0,
    wealth: vested + etfValue
  }
})
const unpriced = computed(() => heldEtfs.value.filter(e => !e.live_price).map(e => e.ticker))

const PALETTE = ['#4a90e2', '#50e3c2', '#f5a623', '#9b59b6', '#27ae60', '#e67e22',
  '#1abc9c', '#e74c3c', '#34495e', '#f1c40f', '#7f8c8d', '#d35400']

const fetchPortfolio = async () => {
  try {
    const res = await api.get(`/investments/dashboard-summary`)
    portfolio.value = res.data
  } catch (e) {
    console.error("Error fetching portfolio:", e)
  }
}

const formatCurrency = (amount) => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR'
  }).format(amount || 0)
}

const formatPercentage = (pct) => {
  return (pct || 0).toFixed(2) + '%'
}

const renderEtfCharts = () => {
  const commonOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {legend: {position: 'bottom'}}
  }

  // Allocation across everything owned now: each ETF/stock and the
  // vested employee shares per ticker.
  const slices = [
    ...heldEtfs.value.filter(e => e.current_value > 0)
      .map(e => ({label: e.ticker, value: e.current_value})),
    ...portfolio.value.shares.filter(s => s.available_value > 0)
      .map(s => ({label: `${s.ticker} (vested)`, value: s.available_value}))
  ].sort((a, b) => b.value - a.value)
  if (allocationChartInstance) allocationChartInstance.destroy()
  allocationChartInstance = slices.length && chartAllocation.value ? new Chart(chartAllocation.value, {
    type: 'doughnut',
    data: {
      labels: slices.map(x => x.label),
      datasets: [{
        data: slices.map(x => x.value),
        backgroundColor: slices.map((_, i) => PALETTE[i % PALETTE.length])
      }]
    },
    options: {
      ...commonOptions,
      plugins: {
        legend: {position: 'bottom'},
        tooltip: {callbacks: {label: (ctx) => `${ctx.label}: ${formatCurrency(ctx.parsed)}`}}
      }
    }
  }) : null

  const held = [...heldEtfs.value].sort((a, b) => b.current_value - a.current_value)
  if (investedChartInstance) investedChartInstance.destroy()
  investedChartInstance = held.length && chartInvested.value ? new Chart(chartInvested.value, {
    type: 'bar',
    data: {
      labels: held.map(e => e.ticker),
      datasets: [
        {label: 'Invested (€)', data: held.map(e => e.total_invested), backgroundColor: '#95a5a6'},
        {label: 'Current Value (€)', data: held.map(e => e.current_value), backgroundColor: '#4a90e2'}
      ]
    },
    options: {
      ...commonOptions,
      scales: {y: {beginAtZero: true, ticks: {callback: (v) => v.toLocaleString('de-DE') + ' €'}}},
      plugins: {
        legend: {position: 'bottom'},
        tooltip: {callbacks: {label: (ctx) => `${ctx.dataset.label}: ${formatCurrency(ctx.parsed.y)}`}}
      }
    }
  }) : null
}

const renderCharts = async () => {
  await nextTick() // Ensure DOM is ready
  renderEtfCharts()
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
        label: 'Vested Value (€)',
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
        label: 'Unvested Value (€)',
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
              callback: (value) => value.toLocaleString('de-DE') + ' €'
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
      <div class="section highlight wealth" v-if="portfolio.timestamp">
        <h3>Total Wealth</h3>
        <div class="wealth-total">{{ formatCurrency(totals.wealth) }}</div>
        <div class="wealth-grid">
          <div class="wealth-item">
            <span class="wealth-label">Employee shares (vested)</span>
            <span class="wealth-value">{{ formatCurrency(totals.vested) }}</span>
            <span class="wealth-note" v-if="totals.unvested > 0">+ {{ formatCurrency(totals.unvested) }} unvested, not counted</span>
          </div>
          <div class="wealth-item">
            <span class="wealth-label">ETFs &amp; stocks</span>
            <span class="wealth-value">{{ formatCurrency(totals.etfValue) }}</span>
            <span class="wealth-note">Invested {{ formatCurrency(totals.invested) }}</span>
          </div>
          <div class="wealth-item">
            <span class="wealth-label">ETFs &amp; stocks return</span>
            <span class="wealth-value" :class="totals.etfReturn >= 0 ? 'positive' : 'negative'">
              {{ formatCurrency(totals.etfReturn) }} ({{ formatPercentage(totals.etfReturnPct) }})
            </span>
            <span class="wealth-note">Includes sold and liquidated funds</span>
          </div>
        </div>
        <p class="wealth-warning" v-if="unpriced.length">No price for {{ unpriced.join(', ') }}: counted as €0. Set its ticker in Admin → Instruments.</p>
      </div>

      <div class="section" v-if="heldEtfs.length > 0 || totals.vested > 0">
        <h3>Allocation</h3>
        <div class="charts-grid">
          <div class="chart-box">
            <h4>Everything owned now</h4>
            <div class="canvas-wrapper">
              <canvas ref="chartAllocation"></canvas>
            </div>
          </div>
          <div class="chart-box" v-if="heldEtfs.length > 0">
            <h4>ETFs &amp; stocks: invested vs current value</h4>
            <div class="canvas-wrapper">
              <canvas ref="chartInvested"></canvas>
            </div>
          </div>
        </div>
      </div>

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

/* Total wealth */
.wealth-total {
  font-size: 2rem;
  font-weight: 700;
  color: #333;
  margin-bottom: 16px;
}

.wealth-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.wealth-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wealth-label {
  font-size: 0.85rem;
  color: #666;
}

.wealth-value {
  font-size: 1.2rem;
  font-weight: 600;
}

.wealth-note {
  font-size: 0.8rem;
  color: #888;
}

.wealth-warning {
  margin: 16px 0 0;
  color: #e67e22;
  font-size: 0.9rem;
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
