// Pipeline steps for a running job (design v2 A1, D3): done steps full, the current one filled by its own progress
// with its detail ("200 of 649") underneath, later steps empty. The backend reports the step as
// "Calibrate (200 of 649)", so steps are matched by name, not by the whole string.

export function stepState(steps: string[], step: string | null | undefined) {
  const idx = step ? steps.findIndex((s) => step === s || step.startsWith(`${s} `)) : -1
  const detail =
    idx >= 0 && step
      ? step
          .slice(steps[idx].length)
          .trim()
          .replace(/^\((.*)\)$/, '$1')
      : ''
  const m = /(\d[\d,]*)\s+of\s+(\d[\d,]*)/.exec(detail)
  const frac = m ? Number(m[1].replace(/,/g, '')) / Math.max(1, Number(m[2].replace(/,/g, ''))) : null
  return { idx, detail, frac }
}

export function Steps({
  steps,
  step,
  cls,
}: {
  steps: string[]
  step: string | null | undefined
  cls: { steps: string; step?: string; bar: string; fill: string; done: string; now: string; muted: string }
}) {
  const { idx, detail, frac } = stepState(steps, step)
  return (
    <div className={cls.steps}>
      {(steps ?? []).map((st, i) => (
        <div key={st} className={cls.step}>
          <span className={`${cls.bar} ${i < idx ? cls.done : ''}`}>
            {i === idx && (
              <span
                className={`${cls.fill} ${cls.now}`}
                style={{ width: `${frac != null ? Math.max(4, frac * 100) : 100}%` }}
              />
            )}
          </span>
          <span className={i <= idx ? undefined : cls.muted}>{st}</span>
          {i === idx && detail && <span className={cls.muted}>{detail}</span>}
        </div>
      ))}
    </div>
  )
}
