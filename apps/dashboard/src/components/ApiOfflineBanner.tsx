import { WifiOff } from 'lucide-react';

export function ApiOfflineBanner() {
  return (
    <div className="bg-red-50 border-b border-red-200 px-4 py-2.5 flex items-center justify-center gap-2">
      <WifiOff className="w-4 h-4 text-red-500" />
      <p className="text-sm text-red-700 font-medium">
        API is offline — data may be stale or unavailable
      </p>
    </div>
  );
}
