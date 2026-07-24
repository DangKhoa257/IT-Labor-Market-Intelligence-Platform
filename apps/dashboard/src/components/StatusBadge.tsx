import { Badge } from './Badge';

interface StatusBadgeProps {
  status: string;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const variant = status === 'ACTIVE' ? 'success' : status === 'EXPIRED' ? 'danger' : 'default';
  return <Badge variant={variant}>{status}</Badge>;
}
