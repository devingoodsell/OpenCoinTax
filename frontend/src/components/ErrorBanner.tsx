export default function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="bg-danger-subtle rounded-lg p-4 text-sm"
      style={{ color: "var(--danger)", border: "1px solid rgba(239, 68, 68, 0.2)" }}
    >
      <p>{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 underline text-xs transition-colors"
          style={{ color: "var(--danger)" }}
        >
          Retry
        </button>
      )}
    </div>
  );
}
