// The sub viewer's display levels (012-DR-08): an SVG filter the images use, and the compact sliders that set it.
import { useId } from 'react'
import { Button } from '../../components/ui'
import {
  BLACK_MAX,
  BLACK_MIN,
  BRIGHT_MAX,
  BRIGHT_MIN,
  isNeutral,
  type Levels,
  NEUTRAL,
  signed,
  tableValues,
} from './levels'
import s from './sub.module.css'

/** A filter id safe in CSS url(#…). */
export function useFilterId(): string {
  return `sub-levels-${useId().replace(/[^a-zA-Z0-9]/g, '')}`
}

/** The curve as an SVG filter (feComponentTransfer, worked on the 8-bit sRGB values as stored, the same table for
 * red, green and blue so a mono preview stays grey). Nothing is drawn while the levels are neutral. */
export function LevelsFilter({ id, levels }: { id: string; levels: Levels }) {
  if (isNeutral(levels)) return null
  const table = tableValues(levels)
  return (
    <svg className={s.filterDefs} aria-hidden="true" focusable="false">
      <filter id={id} colorInterpolationFilters="sRGB">
        <feComponentTransfer>
          <feFuncR type="table" tableValues={table} />
          <feFuncG type="table" tableValues={table} />
          <feFuncB type="table" tableValues={table} />
        </feComponentTransfer>
      </filter>
    </svg>
  )
}

/** The CSS filter for an image: none while neutral. */
export function levelsFilter(id: string, levels: Levels): string | undefined {
  return isNeutral(levels) ? undefined : `url(#${id})`
}

export function LevelsControl({ levels, onChange }: { levels: Levels; onChange: (l: Levels) => void }) {
  return (
    <div className={s.levels} role="group" aria-label="Display levels (this screen only)">
      <label className={s.level}>
        <span>Black point</span>
        <input
          type="range"
          min={BLACK_MIN}
          max={BLACK_MAX}
          step={1}
          value={levels.black}
          aria-valuetext={`Black point ${signed(levels.black)}`}
          title="Black point: [ and ] nudge it"
          onChange={(e) => onChange({ ...levels, black: Number(e.target.value) })}
        />
        <span className={s.levelValue} aria-hidden="true">
          {signed(levels.black)}
        </span>
      </label>
      <label className={s.level}>
        <span>Brightness</span>
        <input
          type="range"
          min={BRIGHT_MIN}
          max={BRIGHT_MAX}
          step={1}
          value={levels.bright}
          aria-valuetext={`Brightness ${signed(levels.bright)}`}
          onChange={(e) => onChange({ ...levels, bright: Number(e.target.value) })}
        />
        <span className={s.levelValue} aria-hidden="true">
          {signed(levels.bright)}
        </span>
      </label>
      <Button
        size="sm"
        variant="link"
        disabled={isNeutral(levels)}
        onClick={() => onChange(NEUTRAL)}
        title="Reset (\)"
      >
        Reset
      </Button>
    </div>
  )
}
