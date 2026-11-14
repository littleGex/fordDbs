// Start date (YYYY-MM-DD) of the dashboard's history chart ranges.
// Steps back whole months and clamps to the target month's last day, so
// 31 March - 1 month is 28 February, not 3 March (#57).
const pad = (n) => String(n).padStart(2, '0')
const MONTHS_BACK = {'1M': 1, '6M': 6, '1Y': 12}

export const rangeStart = (range, asOf) => {
  const [year, month, day] = asOf.split('-').map(Number)
  if (range === 'YTD') return `${year}-01-01`
  const back = MONTHS_BACK[range]
  if (!back) return ''
  const index = year * 12 + (month - 1) - back
  const y = Math.floor(index / 12)
  const m = index % 12 + 1
  const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate()
  return `${y}-${pad(m)}-${pad(Math.min(day, lastDay))}`
}
