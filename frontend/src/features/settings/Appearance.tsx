// Settings → Appearance (design v2 A4, 008-DR-08): Dark, Light and Night vision; N toggles night vision anywhere.
import { useAppTheme } from '../../design/ThemeContext'
import type { Theme } from '../../design/theme'
import v from '../v2/v2.module.css'
import { SettingsSection } from './SettingsSection'

const OPTIONS: [Theme, string][] = [
  ['dark', 'Dark'],
  ['light', 'Light'],
  ['night', 'Night vision'],
]

export function Appearance() {
  const { theme, setTheme } = useAppTheme()
  return (
    <SettingsSection id="appearance" title="Appearance">
      <div className={v.pills} role="group" aria-label="Theme">
        {OPTIONS.map(([t, label]) => (
          <button
            key={t}
            type="button"
            aria-pressed={theme === t}
            className={v.pill}
            onClick={() => setTheme(t)}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="muted">
        Press <kbd>N</kbd> anywhere for night vision.
      </p>
    </SettingsSection>
  )
}
