import { useAnalyticsSalaries, useAnalyticsOverview } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { LimitationsPanel } from '../components/LimitationsPanel';
import { StatCard } from '../components/StatCard';
import { ChartCard } from '../components/ChartCard';
import { CardSkeleton } from '../components/LoadingSkeleton';
import { ErrorState } from '../components/ErrorState';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { formatCurrency } from '../utils/format';
import type { ValueType } from 'recharts/types/component/DefaultTooltipContent';
import type { SalaryCurrencyItem, SalaryCategoryItem, SalaryCityItem } from '../types/api';

export function SalariesPage() {
  const { data: salaries, isLoading: salariesLoading, error: salariesError } = useAnalyticsSalaries();
  const { data: overview, isLoading: overviewLoading } = useAnalyticsOverview();

  if (salariesError) {
    return <ErrorState message="Failed to load salaries data." />;
  }

  return (
    <div className="space-y-8 pb-12">
      <PageHeader 
        title="Salary Analysis" 
        description="Compensation trends across categories and locations." 
      />

      {overviewLoading ? <CardSkeleton /> : overview && (
        <LimitationsPanel 
          sampleSize={overview.sample_size ?? overview.data.total_jobs} 
          limitations={overview.limitations ?? []} 
          generatedAt={overview.generated_at} 
        />
      )}

      {overview && !overviewLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <StatCard 
            label="Salary Disclosed Rate" 
            value={`${(overview.data.salary_disclosed_rate * 100).toFixed(1)}%`} 
          />
          <StatCard 
            label="Undisclosed Rate" 
            value={`${((1 - overview.data.salary_disclosed_rate) * 100).toFixed(1)}%`} 
          />
        </div>
      )}

      {salariesLoading ? (
        <div className="space-y-6"><CardSkeleton /><CardSkeleton /></div>
      ) : salaries?.data?.by_currency ? (
        salaries.data.by_currency.map((currencyData: SalaryCurrencyItem) => {
          const currency = currencyData.currency;
          const categoryData = salaries.data.by_category?.filter((c: SalaryCategoryItem) => c.currency === currency) || [];
          const cityData = salaries.data.by_city?.filter((c: SalaryCityItem) => c.currency === currency) || [];

          return (
            <div key={currency} className="space-y-6">
              <div className="border-b border-gray-200 pb-2">
                <h2 className="text-2xl font-semibold text-gray-900">{currency} Salaries</h2>
                {currencyData.sample_count < 5 && (
                  <p className="text-sm text-yellow-700 mt-1">
                    {currencyData.interpretation} Values use the {currencyData.calculation_basis.replace(/_/g, ' ')}.
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
                <StatCard label="Sample Count" value={currencyData.sample_count.toLocaleString()} />
                <StatCard label="Min" value={formatCurrency(currencyData.min, currency)} />
                <StatCard label="Max" value={formatCurrency(currencyData.max, currency)} />
                <StatCard label="Mean" value={formatCurrency(currencyData.mean, currency)} />
                <StatCard label="Median" value={formatCurrency(currencyData.median, currency)} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ChartCard title="Salary by Category (Median)">
                  <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={categoryData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" />
                        <YAxis dataKey="category" type="category" width={100} tick={{fontSize: 12}} />
                        <Tooltip formatter={(value: ValueType | undefined) => typeof value === 'number' ? formatCurrency(value, currency) : value as React.ReactNode} />
                        <Bar dataKey="median" fill="#6366f1" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartCard>
                
                <ChartCard title="Salary by City (Median)">
                  <div className="h-[300px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={cityData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" />
                        <YAxis dataKey="city" type="category" width={100} tick={{fontSize: 12}} />
                        <Tooltip formatter={(value: ValueType | undefined) => typeof value === 'number' ? formatCurrency(value, currency) : value as React.ReactNode} />
                        <Bar dataKey="median" fill="#818cf8" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </ChartCard>
              </div>
            </div>
          );
        })
      ) : null}
    </div>
  );
}
