<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import axios from 'axios'
import Chart from 'chart.js/auto'

const portfolio = ref({ shares: [], etfs: [], timestamp: '' })
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
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

const formatPercentage = (pct) => {
  return pct.toFixed(2) + '%'
}

// Chart Generation Logic
const renderCharts = () => {
  if (!portfolio.value.shares || portfolio.value.shares.length === 0) return;

  const labels = portfolio.value.shares.map(s => s.ticker)

  // Calculate Data arrays
  const totalShares = portfolio.value.shares.map(s => s.available_shares + s.pending_shares)
  const totalValue = portfolio.value.shares.map(s => (s.available_shares + s.pending_shares) * (s.live_price || 0))

  const availableShares = portfolio.value.shares.map(s => s.available_shares)
  const availableValue = portfolio.value.shares.map(s => s.available_value || 0)

  const pendingShares = portfolio.value.shares.map(s => s.pending_shares)
  const pendingValue = portfolio.value.shares.map(s => s.pending_shares * (s.live_price || 0))

  const createChart = (instance, canvasRef, title, labelAmount, dataAmount, labelValue, dataValue) => {
    if (instance) instance.destroy();
    return new Chart(canvasRef.value, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: labelAmount,
            data: dataAmount,
            backgroundColor: 'rgba(54, 162, 235, 0.6)',
            yAxisID: 'y'
          },
          {
            label: labelValue,
            data: dataValue,
            backgroundColor: 'rgba(75, 192, 192, 0.6)',
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        plugins: { title: { display: true, text: title, font: { size: 16 } } },
        scales: {
          y: { type: 'linear', display: true, position: 'left', title: { display: true, text: 'Shares' } },
          y1: { type: 'linear', display: true, position: 'right', title: { display: true, text: 'Value ($)' }, grid: { drawOnChartArea: false } }
        }
      }
    });
  }

  totalChartInstance = createChart(totalChartInstance, chartTotal, 'Total Portfolio', 'Total Shares', totalShares, 'Total Value ($)', totalValue);
  availableChartInstance = createChart(availableChartInstance, chartAvailable, 'Available Shares Only', 'Available Shares', availableShares, 'Available Value ($)', availableValue);
  pendingChartInstance = createChart(pendingChartInstance, chartPending, 'Pending/Unavailable Shares Only', 'Pending Shares', pendingShares, 'Pending Value ($)', pendingValue);
}

// Watch for data changes to draw/redraw charts
watch(() => portfolio.value.shares, async (newVal) => {
  console.log("Shares updated, rendering charts...", newVal);
  await nextTick();
  renderCharts();
}, { deep: true });

onMounted(fetchPortfolio)
</script>

<template>
  <div class="dashboard">
    <h2>Portfolio Overview</h2>
    <p class="timestamp">Last updated: {{ new Date(portfolio.timestamp).toLocaleString() }}</p>

    <div class="sections">

      <div class="section" v-if="portfolio.shares.length > 0">
        <h3>Share Analytics</h3>
        <div class="charts-grid">
          <div class="chart-container">
            <h4>Total Share Value (Vested + Pending)</h4>
            <canvas ref="chartTotal"></canvas>
          </div>
          <div class="chart-container">
            <h4>Available Share Value</h4>
            <canvas ref="chartAvailable"></canvas>
          </div>
          <div class="chart-container">
            <h4>Pending Share Value</h4>
            <canvas ref="chartPending"></canvas>
          </div>
        </div>
      </div>

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
                <td>{{ share.available_shares.toFixed(6) }}</td>
                <td>{{ share.pending_shares.toFixed(6) }}</td>
                <td>{{ formatCurrency(share.live_price) }}</td>
                <td>{{ formatCurrency(share.available_value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      </div>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1200px; margin: 0 auto; padding-bottom: 40px; }
.timestamp { color: #666; font-size: 0.9rem; margin-bottom: 20px; }
.sections { display: grid; gap: 30px; }
.section { background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
.section h3 { margin-top: 0; color: #2d3436; }
.empty { text-align: center; color: #999; padding: 20px; }

/* Table Styling */
.table-container {
  width: 100%;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.portfolio-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
.portfolio-table th, .portfolio-table td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
.portfolio-table th { background-color: #f8f9fa; font-weight: 600; color: #2d3436; }
.positive { color: #27ae60; font-weight: bold; }
.negative { color: #e74c3c; font-weight: bold; }

/* Chart Styling */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
  margin-top: 15px;
}
.chart-container {
  background: #fdfdfd;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 10px;
}
canvas {
  min-height: 250px !important;
  width: 100% !important;
  background: #fafafa;
}
/* 3. General spacing for smaller screens */
@media (max-width: 600px) {
  .dashboard {
    padding: 10px;
  }

  .section {
    padding: 15px;
    margin-bottom: 20px;
  }

  .portfolio-table th, .portfolio-table td {
    padding: 8px;
    font-size: 0.85rem; /* Smaller text for mobile */
  }
}
</style>
