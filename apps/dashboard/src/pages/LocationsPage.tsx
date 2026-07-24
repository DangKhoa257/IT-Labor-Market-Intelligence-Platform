import { useAnalyticsLocations } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { ChartCard } from '../components/ChartCard';
import { CardSkeleton } from '../components/LoadingSkeleton';
import { DataTable, type Column } from '../components/DataTable';
import { ErrorState } from '../components/ErrorState';
import { LimitationsPanel } from '../components/LimitationsPanel';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import type { ValueCount } from '../types/api';

const COLORS = ['#4f46e5', '#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe'];

export function LocationsPage() {
  const { data: locations, isLoading, error } = useAnalyticsLocations();

  const cityColumns: Column<ValueCount>[] = [
    {
      key: 'city',
      header: 'City',
      render: (row) => <span className="font-semibold text-navy-900">{row.value || 'Unspecified'}</span>,
    },
    {
      key: 'count',
      header: 'Job Count',
      render: (row) => row.count.toLocaleString(),
    },
  ];

  return (
    <div className="space-y-8 pb-12">
      <PageHeader 
        title="Locations & Work Arrangements" 
        description="Geographic breakdown of IT job postings across cities, provinces, and remote/onsite work modes." 
      />

      {isLoading ? (
        <div className="space-y-6"><CardSkeleton /><CardSkeleton /></div>
      ) : error ? (
        <ErrorState message="Failed to load location analytics data." />
      ) : locations ? (
        <>
          <LimitationsPanel
            sampleSize={locations.sample_size}
            limitations={locations.limitations}
            generatedAt={locations.generated_at}
          />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <ChartCard title="Jobs by City" sampleSize={locations.sample_size}>
                <div className="h-[320px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={locations.cities} margin={{ top: 10, right: 30, left: 0, bottom: 25 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                      <XAxis dataKey="value" tick={{ fontSize: 12, fill: '#475569' }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#475569' }} />
                      <Tooltip formatter={(val) => [val ?? 0, 'Job Count']} />
                      <Bar dataKey="count" name="Jobs" fill="#4f46e5" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>

              <ChartCard title="Jobs by Province" sampleSize={locations.sample_size}>
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={locations.provinces} layout="vertical" margin={{ top: 10, right: 30, left: 40, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                      <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: '#475569' }} />
                      <YAxis dataKey="value" type="category" tick={{ fontSize: 12, fill: '#475569' }} width={110} />
                      <Tooltip formatter={(val) => [val ?? 0, 'Job Count']} />
                      <Bar dataKey="count" name="Jobs" fill="#6366f1" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>
            </div>

            <div className="space-y-6">
              <ChartCard title="Work Mode Distribution" sampleSize={locations.sample_size}>
                <div className="h-[300px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={locations.work_modes}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={95}
                        paddingAngle={2}
                        dataKey="count"
                        nameKey="value"
                        label={({ name, percent }) => `${name ?? 'Unspecified'}: ${((percent ?? 0) * 100).toFixed(0)}%`}
                      >
                        {locations.work_modes.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(val) => [val ?? 0, 'Job Count']} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>

              <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                <div className="px-5 py-3 border-b border-gray-100 bg-gray-50">
                  <h3 className="text-sm font-semibold text-navy-800">City Breakdown Table</h3>
                </div>
                <DataTable
                  columns={cityColumns}
                  data={locations.cities}
                  keyExtractor={(item) => item.value || 'unspecified'}
                />
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
