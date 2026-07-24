interface LoadingSkeletonProps {
  lines?: number;
  className?: string;
}

export function LoadingSkeleton({ lines = 4, className = '' }: LoadingSkeletonProps) {
  return (
    <div className={`animate-pulse space-y-3 ${className}`} role="status" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="h-4 bg-gray-200 rounded"
          style={{ width: `${80 - i * 10}%` }}
        />
      ))}
      <span className="sr-only">Loading...</span>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse" role="status" aria-label="Loading">
      <div className="h-3 bg-gray-200 rounded w-24 mb-3" />
      <div className="h-7 bg-gray-200 rounded w-16 mb-2" />
      <div className="h-2.5 bg-gray-200 rounded w-32" />
      <span className="sr-only">Loading...</span>
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-2" role="status" aria-label="Loading">
      <div className="h-10 bg-gray-100 rounded" />
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-12 bg-gray-50 rounded" />
      ))}
      <span className="sr-only">Loading...</span>
    </div>
  );
}
