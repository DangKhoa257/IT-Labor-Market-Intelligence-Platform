export function formatCurrency(value: number, currency: string): string {
  if (currency === 'VND') {
    return new Intl.NumberFormat('vi-VN', {
      style: 'currency',
      currency: 'VND',
      maximumFractionDigits: 0,
    }).format(value);
  }
  if (currency === 'USD') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }).format(value);
  }
  return `${value.toLocaleString()} ${currency}`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

export function formatPercentage(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatDate(dateString: string | null): string {
  if (!dateString) return '—';
  try {
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    }).format(new Date(dateString));
  } catch {
    return '—';
  }
}

export function formatDateTime(dateString: string | null): string {
  if (!dateString) return '—';
  try {
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(dateString));
  } catch {
    return '—';
  }
}

export function formatSalaryRange(
  min: number | null,
  max: number | null,
  currency: string | null
): string {
  if (min === null || max === null || currency === null) return 'Undisclosed';
  if (min === max) return formatCurrency(min, currency);
  return `${formatCurrency(min, currency)} — ${formatCurrency(max, currency)}`;
}

export function timeAgo(dateString: string | null): string {
  if (!dateString) return '—';
  try {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return formatDate(dateString);
  } catch {
    return '—';
  }
}
