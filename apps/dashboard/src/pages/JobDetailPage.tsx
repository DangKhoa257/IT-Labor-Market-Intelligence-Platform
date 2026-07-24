import { useParams, useNavigate, Link } from 'react-router-dom';
import { useJobDetail } from '../hooks/useApi';
import { PageHeader } from '../components/PageHeader';
import { Badge } from '../components/Badge';
import { StatusBadge } from '../components/StatusBadge';
import { CardSkeleton } from '../components/LoadingSkeleton';
import { ErrorState } from '../components/ErrorState';
import { formatSalaryRange, formatDate } from '../utils/format';

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = Number(id) || 0;
  const navigate = useNavigate();
  const { data: job, isLoading, error } = useJobDetail(jobId);

  if (isLoading) return <div className="p-6"><CardSkeleton /></div>;
  if (error || !job) return <div className="p-6"><ErrorState message="Job not found or failed to load." /></div>;

  const title = job.title_normalized || job.title_raw;

  return (
    <div className="space-y-6 pb-12">
      <div>
        <button 
          type="button"
          onClick={() => navigate('/jobs')} 
          className="text-accent-600 hover:text-accent-800 text-sm mb-4 font-medium cursor-pointer flex items-center gap-1"
        >
          &larr; Back to Job Explorer
        </button>
        <PageHeader title={title} description={`Source Job ID: ${job.source_job_id}`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h3 className="text-base font-semibold text-navy-900 mb-4">Job Details</h3>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-6">
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Company</dt>
                <dd className="mt-1 text-sm text-navy-800 font-medium">
                  {job.company ? (
                    <Link to={`/companies/${job.company.id}`} className="text-accent-600 hover:underline">
                      {job.company.name}
                    </Link>
                  ) : (
                    'Unspecified'
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Status</dt>
                <dd className="mt-1 text-sm"><StatusBadge status={job.status} /></dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Primary Category</dt>
                <dd className="mt-1 text-sm text-navy-800">{job.primary_category || 'Unclassified'}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">City</dt>
                <dd className="mt-1 text-sm text-navy-800">{job.city || 'Unspecified'}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Work Mode</dt>
                <dd className="mt-1 text-sm text-navy-800">{job.work_mode || 'Unspecified'}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Employment Type</dt>
                <dd className="mt-1 text-sm text-navy-800">{job.employment_type || 'Unspecified'}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Disclosed Salary Range</dt>
                <dd className="mt-1 text-sm font-semibold text-emerald-700">
                  {formatSalaryRange(job.salary_min, job.salary_max, job.salary_currency)}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Salary Status</dt>
                <dd className="mt-1 text-sm text-navy-800">
                  {job.salary_disclosed ? 'Disclosed' : 'Undisclosed / Hidden'}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Posted Date</dt>
                <dd className="mt-1 text-sm text-navy-800">{formatDate(job.posted_at)}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500 uppercase tracking-wider">Collected Date</dt>
                <dd className="mt-1 text-sm text-navy-800">{formatDate(job.collected_at)}</dd>
              </div>
            </dl>
          </div>

          {job.description_preview && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <h3 className="text-base font-semibold text-navy-900 mb-3">Description Preview</h3>
              <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-4 rounded-lg border border-gray-100 font-mono text-xs">
                {job.description_preview}
              </p>
            </div>
          )}
        </div>

        <div className="space-y-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h3 className="text-base font-semibold text-navy-900 mb-4">Extracted Canonical Skills</h3>
            {job.skills && job.skills.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {job.skills.map((skillName, idx) => (
                  <Badge key={idx} variant="primary">{skillName}</Badge>
                ))}
              </div>
            ) : (
              <span className="text-sm text-gray-500">No canonical skills extracted for this posting.</span>
            )}
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
            <h3 className="text-base font-semibold text-navy-900 mb-2">Reference Links</h3>
            {job.company && (
              <Link 
                to={`/companies/${job.company.id}`}
                className="block text-sm text-accent-600 hover:text-accent-800 font-medium"
              >
                View Company Profile &rarr;
              </Link>
            )}
            {job.source_url && (
              <a 
                href={job.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-sm text-accent-600 hover:text-accent-800 font-medium"
              >
                View Original Posting on TopDev &nearr;
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
