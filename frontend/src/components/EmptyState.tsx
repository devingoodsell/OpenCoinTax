import { Link } from "react-router-dom";

export default function EmptyState({
  title,
  description,
  actionLabel,
  actionTo,
}: {
  title: string;
  description?: string;
  actionLabel?: string;
  actionTo?: string;
}) {
  return (
    <div className="text-center py-16" style={{ color: "var(--text-muted)" }}>
      <h3 className="text-lg font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
        {title}
      </h3>
      {description && <p className="text-sm mb-4">{description}</p>}
      {actionLabel && actionTo && (
        <Link
          to={actionTo}
          className="inline-block px-4 py-2 text-white rounded text-sm transition-colors"
          style={{ backgroundColor: "var(--accent)" }}
        >
          {actionLabel}
        </Link>
      )}
    </div>
  );
}
