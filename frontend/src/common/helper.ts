import { ref } from 'vue'
import type { WireGuardSummary } from './packetHandler'

export const formatBytes = (value?: number | string | null): string => {
  if (value === undefined || value === null) return '—'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '—'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let unit = 0
  let result = numeric
  while (Math.abs(result) >= 1024 && unit < units.length - 1) {
    result /= 1024
    unit += 1
  }
  return `${result.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[unit]}`
}

export const formatRate = (value?: number | string | null): string => {
  if (value === undefined || value === null || !Number.isFinite(Number(value))) return '—'
  return `${formatBytes(value)}/s`
}

export const formatEpoch = (value?: number | string | null): string => {
  if (!value) return '—'
  const milliseconds = Number(value) * 1000
  if (!Number.isFinite(milliseconds)) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(milliseconds),
  )
}

export const formatHandshake = (
  status?: { wireguard?: WireGuardSummary } | null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  t?: (key: any) => string,
): string => {
  const age = status?.wireguard?.latest_handshake_age_seconds
  if (age !== undefined && age !== null) {
    const numeric = Number(age)
    if (!Number.isFinite(numeric)) return '—'
    if (numeric < 60) return `${Math.round(numeric)} ${t?.('time.seconds') ?? 'seconds'}`
    if (numeric < 3600) return `${Math.round(numeric / 60)} ${t?.('time.minutes') ?? 'minutes'}`
    if (numeric < 86400) return `${Math.round(numeric / 3600)} ${t?.('time.hours') ?? 'hours'}`
    return `${Math.round(numeric / 86400)} ${t?.('time.days') ?? 'days'}`
  }
  return formatEpoch(status?.wireguard?.latest_handshake_seconds)
}

export const nodeTitle = (node: { name: string; peering?: { display_name?: string | null } | null }): string =>
  node.peering?.display_name || node.name

// --- Theme management ---

const SUPPORTED_THEMES = ['light', 'dark'] as const
export type ThemeName = (typeof SUPPORTED_THEMES)[number]

export const THEME_STORAGE_KEY = 'theme'
export const themeName = ref<ThemeName>('light')

export const isValidTheme = (candidate: unknown): candidate is ThemeName =>
  typeof candidate === 'string' && (SUPPORTED_THEMES as readonly string[]).includes(candidate)

export const applyTheme = (newThemeName?: string, persist = false): void => {
  themeName.value = isValidTheme(newThemeName) ? newThemeName : 'light'
  if (persist && typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, themeName.value)
    } catch (error) {
      console.warn('Failed to persist theme preference', error)
    }
  }
}
