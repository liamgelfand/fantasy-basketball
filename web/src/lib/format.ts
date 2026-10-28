/** Ratio categories read best with three decimals; counting stats with one. */
export function isRatio(stat: string): boolean {
  return stat.includes('%') || stat === 'A/TO'
}

export function formatStat(stat: string, value: number): string {
  if (isRatio(stat)) return value.toFixed(3).replace(/^0\./, '.')
  return Math.abs(value) >= 100 ? Math.round(value).toLocaleString() : value.toFixed(1)
}

export function pct(p: number, digits = 0): string {
  if (p > 0.995 && digits === 0) return '>99%'
  if (p < 0.005 && p > 0 && digits === 0) return '<1%'
  return `${(p * 100).toFixed(digits)}%`
}

export function signed(value: number, digits = 1): string {
  const s = value.toFixed(digits)
  return value > 0 ? `+${s}` : value === 0 ? (0).toFixed(digits) : s
}

export function signedPct(delta: number, digits = 1): string {
  return `${signed(delta * 100, digits)}%`
}

export function shortDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'numeric', day: 'numeric' })
}

export function longDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

/** Win probability → Mantine color: hot when you're ahead, cold when behind. */
export function probColor(p: number): string {
  if (p >= 0.7) return 'teal'
  if (p >= 0.55) return 'lime'
  if (p > 0.45) return 'yellow'
  if (p > 0.3) return 'orange'
  return 'red'
}

export function probEmoji(p: number): string {
  if (p >= 0.85) return '🔥'
  if (p >= 0.6) return '💪'
  if (p > 0.4) return '⚖️'
  if (p > 0.15) return '😬'
  return '🧊'
}

const ACRONYMS = new Set(['H2H', 'IR', 'FA', 'FAAB', 'ROTO'])

/** ESPN enum strings (DAY_TO_DAY, H2H_POINTS) as readable labels, keeping known acronyms. */
export function titleCase(s: string): string {
  return s
    .split('_')
    .map((w) => (ACRONYMS.has(w.toUpperCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join(' ')
}

/** Stats where a lower number is better. */
export function isReverseStat(stat: string, reverse: Iterable<string> = []): boolean {
  return stat === 'TO' || new Set(reverse).has(stat)
}
