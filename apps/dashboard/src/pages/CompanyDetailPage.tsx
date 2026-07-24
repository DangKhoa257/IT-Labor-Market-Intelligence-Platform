import { useParams, useNavigate } from 'react-router-dom';
import { useCompanyDetail } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { StatCard } from '../components/StatCard';
import { CardSkeleton } from '../components/LoadingSkeleton';
import { ErrorState } from '../components/ErrorState';
import { Badge } from '../components/Badge';

export function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const companyId = Number(id) || 0;
  const navigate = useNavigate();
  const { data: company, isLoading, error } = useCompanyDetail(companyId);

  if (isLoading) return <div className="p-6"><CardSkeleton /></div>;
  if (error || !company) return <div className="p-6"><ErrorState message="Company not found or failed to load." /></div>;

  return (
    <div className="space-y-6 pb-12">
      <div>
        <button 
          type="button"
          onClick={() => navigate('/companies')} 
          className="text-accent-600 hover:text-accent-800 text-sm mb-4 font-medium cursor-pointer"
        >
          &larr; Back to Companies
        </button>
        <PageHeader title={company.name} description={`Company ID #${company.id}`} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatCard label="Total Jobs" value={company.job_count.toLocaleString()} />
        <StatCard label="Active Jobs" value={company.active_job_count.toLocaleString()} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-navy-800 mb-4">Job Categories</h3>
          {company.categories && company.categories.length > 0 ? (
            <ul className="space-y-3">
              {company.categories.map((cat, idx) => (
                <li key={idx} className="flex justify-between items-center text-sm">
                  <span className="text-navy-700">{cat.value || 'Unclassified'}</span>
                  <Badge variant="primary">{cat.count}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No category data available.</p>
          )}
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-navy-800 mb-4">Top Skills Required</h3>
          {company.top_skills && company.top_skills.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {company.top_skills.map((skill, idx) => (
                <div key={idx} className="flex items-center gap-1">
                  <Badge variant="default">{skill.value || 'Unknown'}</Badge>
                  <span className="text-xs text-gray-500">({skill.count})</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">No skill data available.</p>
          )}
        </div>
      </div>

      <div className="pt-4">
        <button
          type="button"
          onClick={() => navigate(`/jobs?company_id=${company.id}`)}
          className="px-4 py-2 bg-accent-600 text-white rounded-lg hover:bg-accent-700 font-medium text-sm transition-colors shadow-sm cursor-pointer"
        >
          View All Jobs
        </button>
      </div>
    </div>
  );
}
