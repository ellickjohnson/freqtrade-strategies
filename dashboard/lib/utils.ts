import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(
  value: number | undefined | null,
  currency: string = 'USD',
  locale: string = 'en-US'
): string {
  if (value === undefined || value === null || isNaN(value)) return '$0.00'
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatPercent(
  value: number | undefined | null,
  decimals: number = 2
): string {
  if (value === undefined || value === null || isNaN(value)) return '+0.00%'
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}%`
}

export function formatNumber(
  value: number,
  decimals: number = 2
): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date))
}

export function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  
  if (hours > 24) {
    const days = Math.floor(hours / 24)
    return `${days}d ${hours % 24}h`
  }
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  
  return `${minutes}m`
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'running':
      return 'text-green-400'
    case 'stopped':
      return 'text-slate-400'
    case 'error':
      return 'text-red-400'
    case 'starting':
    case 'stopping':
      return 'text-yellow-400'
    default:
      return 'text-slate-400'
  }
}

export function getStatusBgColor(status: string): string {
  switch (status) {
    case 'running':
      return 'bg-green-400/10'
    case 'stopped':
      return 'bg-slate-400/10'
    case 'error':
      return 'bg-red-400/10'
    case 'starting':
    case 'stopping':
      return 'bg-yellow-400/10'
    default:
      return 'bg-slate-400/10'
  }
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 3)}...`
}