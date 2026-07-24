import { Route, Routes } from 'react-router-dom';
import { AppShell } from './layouts/AppShell';
import { OverviewPage } from './pages/OverviewPage';
import { JobsPage } from './pages/JobsPage';
import { JobDetailPage } from './pages/JobDetailPage';
import { SkillsPage } from './pages/SkillsPage';
import { SalariesPage } from './pages/SalariesPage';
import { CompaniesPage } from './pages/CompaniesPage';
import { CompanyDetailPage } from './pages/CompanyDetailPage';
import { LocationsPage } from './pages/LocationsPage';
import { QualityPage } from './pages/QualityPage';
import { DuplicatesPage } from './pages/DuplicatesPage';

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="salaries" element={<SalariesPage />} />
        <Route path="companies" element={<CompaniesPage />} />
        <Route path="companies/:id" element={<CompanyDetailPage />} />
        <Route path="locations" element={<LocationsPage />} />
        <Route path="quality" element={<QualityPage />} />
        <Route path="duplicates" element={<DuplicatesPage />} />
      </Route>
    </Routes>
  );
}
