import { useAnalyticsOverview, useAnalyticsCategories, useAnalyticsSkills, useAnalyticsLocations } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { LimitationsPanel } from '../components/LimitationsPanel';
import { StatCard } from '../components/StatCard';
import { ChartCard } from '../components/ChartCard';
import { CardSkeleton } from '../components/LoadingSkeleton';
import { ErrorState } from '../components/ErrorState';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { formatNumber } from '../utils/format';
import { Briefcase, Building2, Code2, BarChart3, DollarSign } from 'lucide-react';

const COLORS = ['#6366f1', '#818cf8', '#a5b4fc', '#c7d2fe', '#e0e7ff'];

export function OverviewPage() {
  const { data: overview, isLoading: overviewLoading, error: overviewError } = useAnalyticsOverview();
  const { data: categories, isLoading: categoriesLoading, error: categoriesError } = useAnalyticsCategories();
  const { data: skills, isLoading: skillsLoading, error: skillsError } = useAnalyticsSkills();
  const { data: locations, isLoading: locationsLoading, error: locationsError } = useAnalyticsLocations();

  if (overviewError || categoriesError || skillsError || locationsError) {
    return <ErrorState message="Failed to load overview data." />;
  }

  return (
    <div className="space-y-6 pb-12">
      <PageHeader 
        title="Market Overview" 
        description="High-level insights from the IT labor market pilot data." 
      />

      {overviewLoading ? (
        <CardSkeleton />
      ) : overview ? (
        <>
          <LimitationsPanel 
            sampleSize={overview.sample_size ?? overview.data.total_jobs} 
            limitations={overview.limitations ?? []} 
            generatedAt={overview.generated_at} 
          />
          
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <StatCard label="Total Jobs" value={formatNumber(overview.data.total_jobs)} icon={Briefcase} />
            <StatCard label="Active Jobs" value={formatNumber(overview.data.active_jobs)} icon={BarChart3} />
            <StatCard label="Unique Companies" value={formatNumber(overview.data.unique_companies)} icon={Building2} />
            <StatCard label="Unique Skills" value={formatNumber(overview.data.unique_skills)} icon={Code2} />
            <StatCard label="Salary Disclosed Rate" value={`${(overview.data.salary_disclosed_rate * 100).toFixed(1)}%`} icon={DollarSign} />
          </div>
        </>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard title="Category Distribution">
          {categoriesLoading ? (
            <CardSkeleton />
          ) : (
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categories?.data} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis dataKey="value" type="category" width={100} tick={{fontSize: 12}} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#6366f1" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>

        <ChartCard title="Top Skills">
          {skillsLoading ? (
            <CardSkeleton />
          ) : (
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={skills?.data.slice(0, 10)} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis dataKey="canonical_name" type="category" width={100} tick={{fontSize: 12}} />
                  <Tooltip />
                  <Bar dataKey="job_count" fill="#818cf8" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>

        <ChartCard title="Location Distribution (Cities)">
          {locationsLoading ? (
            <CardSkeleton />
          ) : (
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={locations?.cities.slice(0,10)} margin={{ top: 5, right: 30, left: 20, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="value" angle={-45} textAnchor="end" tick={{fontSize: 12}} height={60} />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill="#a5b4fc" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>

        <ChartCard title="Work Mode Distribution">
          {locationsLoading ? (
            <CardSkeleton />
          ) : (
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={locations?.work_modes}
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="count"
                    nameKey="value"
                    label={({name, percent}) => percent !== undefined ? `${name} ${(percent * 100).toFixed(0)}%` : name}
                  >
                    {locations?.work_modes.map((_, index: number) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>
      </div>
      
      {overview && (
        <div className="mt-8 text-sm text-gray-500">
          Sample size: {formatNumber(overview.data.total_jobs)} | Last updated: {overview.generated_at ? new Date(overview.generated_at).toLocaleString() : 'N/A'}
        </div>
      )}
    </div>
  );
}
