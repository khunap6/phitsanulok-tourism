interface KPICardProps {
  title: string
  value: string | number
  subtitle?: string
  accentColor?: string
}

export default function KPICard({
  title,
  value,
  subtitle,
  accentColor = '#3b82f6',
}: KPICardProps) {
  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border flex flex-col gap-1">
      <p className="text-brand-subtext text-sm">{title}</p>
      <p
        className="text-3xl font-bold"
        style={{ color: accentColor }}
      >
        {value}
      </p>
      {subtitle && (
        <p className="text-brand-subtext text-xs">{subtitle}</p>
      )}
    </div>
  )
}
