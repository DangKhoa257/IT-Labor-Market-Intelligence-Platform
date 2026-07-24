import { Info } from 'lucide-react';

interface LimitationsPanelProps {
  sampleSize: number;
  limitations: string[];
  generatedAt?: string;
}

export function LimitationsPanel({ sampleSize, limitations, generatedAt }: LimitationsPanelProps) {
  return (
    <div className="bg-sky-50/70 border border-sky-200 rounded-xl p-4">
      <div className="flex gap-3">
        <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
        <div className="text-xs text-sky-800 space-y-1.5">
          <p className="font-semibold">Pilot Dataset Notice</p>
          <p>This dashboard displays data from a pilot sample of <strong>{sampleSize}</strong> job postings. It does not represent the complete Vietnamese IT labor market.</p>
          {limitations.map((l, i) => (
            <p key={i}>• {l}</p>
          ))}
          {generatedAt && (
            <p className="text-sky-600">Generated: {new Date(generatedAt).toLocaleString()}</p>
          )}
        </div>
      </div>
    </div>
  );
}
