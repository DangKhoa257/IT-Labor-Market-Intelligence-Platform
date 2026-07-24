import type {
  HealthResponse,
  JobFilters,
  Page,
  JobDetail,
  CompanyListItem,
  CompanyDetail,
  SkillItem,
  OverviewResponse,
  CategoriesResponse,
  AnalyticsMeta,
  SalariesResponse,
  LocationsResponse,
  QualitySummary,
  DuplicateCluster,
} from '../types/api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new ApiError(response.status, `API error: ${response.status} ${response.statusText}`);
    }

    return response.json() as Promise<T>;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  jobs: (filters?: JobFilters) => {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          params.set(key, String(value));
        }
      });
    }
    const query = params.toString();
    return request<Page>(`/api/v1/jobs${query ? `?${query}` : ''}`);
  },

  jobDetail: (id: number) => request<JobDetail>(`/api/v1/jobs/${id}`),

  companies: () => request<CompanyListItem[]>('/api/v1/companies'),

  companyDetail: (id: number) => request<CompanyDetail>(`/api/v1/companies/${id}`),

  skills: () => request<SkillItem[]>('/api/v1/skills'),

  analyticsOverview: () => request<OverviewResponse>('/api/v1/analytics/overview'),

  analyticsCategories: () => request<CategoriesResponse>('/api/v1/analytics/categories'),

  analyticsSkills: () =>
    request<AnalyticsMeta & { data: SkillItem[] }>('/api/v1/analytics/skills'),

  analyticsSalaries: () => request<SalariesResponse>('/api/v1/analytics/salaries'),

  analyticsLocations: () => request<LocationsResponse>('/api/v1/analytics/locations'),

  qualitySummary: () => request<QualitySummary>('/api/v1/quality/summary'),

  duplicates: () => request<DuplicateCluster[]>('/api/v1/duplicates'),
};
