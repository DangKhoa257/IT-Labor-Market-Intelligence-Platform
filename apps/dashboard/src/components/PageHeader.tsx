interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-6">
      <div>
        <h1 className="text-xl font-semibold text-navy-900 tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-gray-500 mt-1 max-w-2xl">{description}</p>
        )}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}
