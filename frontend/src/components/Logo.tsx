// The SubStation mark drawn inline (brand guide §06), so one drawing serves dark, light and night vision: the
// rear frames take --sst-muted and the front frame and core take --sst-accent, whatever the theme sets them to.
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <rect
        x="3"
        y="3"
        width="13"
        height="13"
        rx="2"
        fill="none"
        stroke="var(--sst-muted)"
        strokeWidth="1.5"
      />
      <rect
        x="5.5"
        y="5.5"
        width="13"
        height="13"
        rx="2"
        fill="none"
        stroke="var(--sst-muted)"
        strokeWidth="1.5"
      />
      <rect
        x="8"
        y="8"
        width="13"
        height="13"
        rx="2"
        fill="none"
        stroke="var(--sst-accent)"
        strokeWidth="2"
      />
      <circle cx="14.5" cy="14.5" r="1.75" fill="var(--sst-accent)" />
    </svg>
  )
}

/** Mark and wordmark: the gap is a third of the mark's height (brand guide §06). */
export function Lockup({ size = 22 }: { size?: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: Math.round(size / 3) }}>
      <Mark size={size} />
      <span
        style={{
          fontSize: Math.round(size * 0.73),
          fontWeight: 600,
          letterSpacing: '-0.01em',
          color: 'var(--sst-text)',
        }}
      >
        SubStation
      </span>
    </span>
  )
}
