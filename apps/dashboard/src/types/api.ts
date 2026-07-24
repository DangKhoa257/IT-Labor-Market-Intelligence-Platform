// Job listing from /api/v1/jobs items
export interface JobOut {
  id: number;
  source_job_id: string;
  source_url: string;
  title_raw: string;
  title_normalized: string | null;
  primary_category: string | null;
  city: string | null;
  work_mode: string | null;
  employment_type: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_disclosed: boolean;
  status: string;
  posted_at: string | null; // ISO datetime
  collected_at: string; // ISO datetime
}

// Job detail from /api/v1/jobs/{job_id}
export interface JobDetail extends JobOut {
  description_preview: string | null;
  skills: string[];
  company: { id: number; name: string } | null;
}

// Paginated response from /api/v1/jobs
export interface Page<T = JobOut> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

// Company list from /api/v1/companies
export interface CompanyListItem {
  id: number;
  name: string;
  job_count: number;
  active_job_count: number;
}

// Company detail from /api/v1/companies/{company_id}
export interface CompanyDetail extends CompanyListItem {
  categories: ValueCount[];
  top_skills: ValueCount[];
}

// Skill from /api/v1/skills
export interface SkillItem {
  id: number;
  canonical_name: string;
  category: string | null;
  job_count: number;
  categories: (string | null)[];
  companies: { id: number; name: string }[];
}

// Shared value-count pair
export interface ValueCount {
  value: string | null;
  count: number;
}

// Source coverage item
export interface SourceCoverage {
  source: string;
  count: number;
}

// Analytics metadata envelope
export interface AnalyticsMeta {
  sample_size: number;
  generated_at: string;
  source_coverage: SourceCoverage[];
  limitations: string[];
}

// /api/v1/analytics/overview
export interface OverviewData {
  total_jobs: number;
  active_jobs: number;
  unique_companies: number;
  unique_skills: number;
  salary_disclosed_rate: number;
  source_coverage: SourceCoverage[];
}

export interface OverviewResponse extends AnalyticsMeta {
  data: OverviewData;
}

// /api/v1/analytics/categories
export interface CategoryItem extends ValueCount {
  percentage: number;
}

export interface CategoriesResponse extends AnalyticsMeta {
  data: CategoryItem[];
}

// /api/v1/analytics/salaries
export interface SalaryCurrencyItem {
  currency: string;
  sample_count: number;
  min: number;
  max: number;
  mean: number;
  median: number;
  calculation_basis: string;
  statistically_meaningful: boolean;
  interpretation: string;
}

export interface SalaryCategoryItem {
  currency: string;
  category: string;
  sample_count: number;
  mean: number;
  median: number;
}

export interface SalaryCityItem {
  currency: string;
  city: string;
  sample_count: number;
  mean: number;
  median: number;
}

export interface SalaryData {
  by_currency: SalaryCurrencyItem[];
  by_category: SalaryCategoryItem[];
  by_city: SalaryCityItem[];
  calculation_metadata: {
    observation_unit: string;
    midpoint_formula: string;
    single_posting_limitation: string;
    currencies_combined: boolean;
  };
}

export interface SalariesResponse extends AnalyticsMeta {
  data: SalaryData;
}

// /api/v1/analytics/locations
export interface LocationsResponse extends AnalyticsMeta {
  cities: ValueCount[];
  provinces: ValueCount[];
  work_modes: ValueCount[];
}

// /api/v1/quality/summary
export interface QualitySummary {
  total_jobs: number;
  accepted_records: number;
  rejected_records: number;
  records_with_info_notices: number;
  records_with_warning_or_error_issues: number;
  title_classified_records: number;
  title_classification_coverage: number;
  issues: { code: string; severity: 'INFO' | 'WARNING' | 'ERROR' | 'REJECT'; count: number }[];
}

// /api/v1/duplicates
export interface DuplicateCluster {
  id: number;
  classification: string;
  score: number | null;
  member_count: number;
  method_version: string | null;
  members: {
    job_id: number;
    source: string;
    source_job_id: string;
    source_url: string;
    representative: boolean;
  }[];
}

// /health
export interface HealthResponse {
  status: string;
}

// Job filters for the explorer
export interface JobFilters {
  page?: number;
  page_size?: number;
  category?: string;
  city?: string;
  company_id?: number;
  skill?: string;
  employment_type?: string;
  work_mode?: string;
  status?: string;
  salary_disclosed?: boolean;
  salary_min?: number;
  salary_max?: number;
  keyword?: string;
  sort?: 'posted_at' | 'collected_at' | 'salary';
  order?: 'asc' | 'desc';
}
