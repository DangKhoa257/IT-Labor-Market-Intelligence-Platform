import { useState, useEffect } from 'react';
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Briefcase,
  Code2,
  DollarSign,
  Building2,
  MapPin,
  ShieldCheck,
  Copy,
  Menu,
  X,
  Database,
} from 'lucide-react';
import { useHealth } from '../hooks/useApi';
import { ApiOfflineBanner } from '../components/ApiOfflineBanner';

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/jobs', label: 'Job Explorer', icon: Briefcase },
  { to: '/skills', label: 'Skills', icon: Code2 },
  { to: '/salaries', label: 'Salaries', icon: DollarSign },
  { to: '/companies', label: 'Companies', icon: Building2 },
  { to: '/locations', label: 'Locations', icon: MapPin },
  { to: '/quality', label: 'Data Quality', icon: ShieldCheck },
  { to: '/duplicates', label: 'Duplicates', icon: Copy },
];

export function AppShell() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const location = useLocation();
  const { data: health, isLoading: isHealthLoading, isError: isHealthError } = useHealth();

  useEffect(() => {
    setIsSidebarOpen(false);
  }, [location.pathname]);

  const toggleSidebar = () => setIsSidebarOpen((prev) => !prev);
  const closeSidebar = () => setIsSidebarOpen(false);

  const getHealthStatus = () => {
    if (isHealthLoading) return 'bg-gray-300';
    if (isHealthError || health?.status !== 'ok') return 'bg-red-500';
    return 'bg-green-500';
  };

  const isOffline = isHealthError || (health && health.status !== 'ok');

  return (
    <div className="flex min-h-screen bg-gray-50 flex-col md:flex-row">
      {/* Mobile Drawer Overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-gray-900/50 lg:hidden"
          onClick={closeSidebar}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 transform transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-auto lg:flex lg:w-64 lg:flex-col ${
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between h-16 px-6 border-b border-gray-200">
          <div className="flex flex-col">
            <span className="text-lg font-semibold text-navy-900">IT Market Intelligence</span>
            <span className="text-xs text-gray-400">Analytics Dashboard</span>
          </div>
          <button
            type="button"
            className="p-2 -mr-2 text-gray-500 rounded-md lg:hidden hover:bg-gray-100 focus:outline-none"
            onClick={closeSidebar}
          >
            <span className="sr-only">Close sidebar</span>
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isActive
                    ? 'bg-accent-50 text-accent-700'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <item.icon
                    className={`w-5 h-5 mr-3 flex-shrink-0 ${
                      isActive ? 'text-accent-700' : 'text-gray-400'
                    }`}
                    aria-hidden="true"
                  />
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Top Header */}
        <header className="flex items-center justify-between h-16 px-4 bg-white border-b border-gray-200 sm:px-6 lg:px-8">
          <div className="flex items-center">
            <button
              type="button"
              className="p-2 -ml-2 text-gray-500 rounded-md lg:hidden hover:bg-gray-100 focus:outline-none"
              onClick={toggleSidebar}
            >
              <span className="sr-only">Open sidebar</span>
              <Menu className="w-5 h-5" />
            </button>
            <h1 className="ml-2 text-lg font-medium text-gray-900 lg:ml-0 md:hidden">
              IT Market Intelligence
            </h1>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center px-2.5 py-1 text-xs font-medium text-navy-700 bg-navy-50 rounded-full border border-navy-200">
              <Database className="w-3.5 h-3.5 mr-1.5" />
              TopDev Pilot
            </div>
            
            <div className="flex items-center text-sm text-gray-500">
              <span className="hidden sm:inline mr-2">API Status:</span>
              <span className="relative flex w-3 h-3">
                <span
                  className={`absolute inline-flex w-full h-full rounded-full opacity-75 ${
                    isHealthLoading
                      ? 'bg-gray-400 animate-ping'
                      : isOffline
                      ? 'bg-red-400 animate-ping'
                      : 'hidden'
                  }`}
                />
                <span
                  className={`relative inline-flex w-3 h-3 rounded-full ${getHealthStatus()}`}
                />
              </span>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto bg-gray-50">
          {isOffline && <ApiOfflineBanner />}
          <div className="max-w-7xl mx-auto p-6 lg:p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
