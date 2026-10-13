// What a reconciliation group is, in words (001-DR-xx, owner 2026-10-11): the kind of file, what it needs and why, and the ignore rules that would take it off the list.
import type { components } from '../../api/schema'
import { signed } from '../format'

export type Example = components['schemas']['ReconExampleOut']

const TYPE_LABEL: Record<string, string> = {
  light: 'Light',
  flat: 'Flat',
  dark: 'Dark',
  dark_flat: 'Dark flat',
  bias: 'Bias',
  master_dark: 'Master dark',
  master_flat: 'Master flat',
  master_bias: 'Master bias',
  master_dark_flat: 'Master dark flat',
  master_light: 'Master light',
  unknown: 'Unknown',
}
export const typeLabel = (t: string | null | undefined) => TYPE_LABEL[t ?? 'unknown'] ?? t ?? 'Unknown'

/** Fields as they read in a sentence. */
const NEED_NAME: Record<string, string> = {
  target: 'target',
  panel: 'panel',
  object: 'object',
  filter: 'filter',
  exptime: 'exposure',
  ccd_temp: 'sensor temperature',
  set_temp: 'temperature',
  gain: 'gain',
  offset: 'offset',
  xbin: 'binning',
  ybin: 'binning',
  camera: 'camera',
  telescope: 'telescope',
  date_obs: 'observation time',
  frame_type: 'frame type',
}

/** "gain", "gain and offset", "gain, offset and temperature" */
export function listText(xs: string[]): string {
  const u = [...new Set(xs)]
  return u.length <= 1 ? (u[0] ?? '') : `${u.slice(0, -1).join(', ')} and ${u[u.length - 1]}`
}

export function tempText(c: number): string {
  return `${signed(c, Number.isInteger(c) ? 0 : 1)} °C`
}

/** One line: what the group needs and why. */
export function needLine(kind: string, field: string | null, ex: Example | null | undefined): string {
  const type = ex?.frame_type ?? 'unknown'
  if (kind === 'missing_field' || kind === 'master_metadata') {
    const own = kind === 'master_metadata' ? ['gain', 'offset', 'set_temp'] : null
    const fields = [field ?? '', ...(ex?.needs ?? [])].filter(
      (f) => f && f !== 'frame_type' && (!own || own.includes(f)),
    )
    const what = listText(fields.map((f) => NEED_NAME[f] ?? f))
    if (type === 'light') return `Needs ${what} before it can join a session.`
    if (type.startsWith('master_')) {
      const t = ex?.set_temp_c ?? ex?.ccd_temp_c
      const shot = t != null && !fields.includes('set_temp') ? ` shot at ${tempText(t)}` : ''
      return `Needs ${what} so it can be matched to lights${shot}.`
    }
    return `Needs ${what} before it can be used for calibration.`
  }
  if (kind === 'classification_unknown') return 'Needs a frame type before it can be used.'
  if (kind === 'frame_missing') return 'Catalogued, but no longer on disk where it was.'
  if (kind === 'ambiguous_master')
    return 'Holds several images and none is marked as the master; the first is used for now.'
  if (kind === 'bad_without_twin') return 'Marked bad in NINA, but the original isn’t in the library.'
  return ''
}

/** A file-name glob for "files like this": digit runs become *, so a night's numbered files share one. Null
 * when what's left is too general to be safe (fewer than three letters before the extension). */
export function likeGlob(name: string): string | null {
  const dot = name.lastIndexOf('.')
  const stem = dot > 0 ? name.slice(0, dot) : name
  const ext = dot > 0 ? name.slice(dot) : ''
  let g = stem.replace(/[[?*]/g, (c) => `[${c}]`).replace(/\d+/g, '*')
  // stars with only punctuation between them say nothing: one star
  for (let prev = ''; prev !== g;) {
    prev = g
    g = g.replace(/\*[^A-Za-z*[\]]*\*/g, '*')
  }
  if ((g.match(/[A-Za-z]/g) ?? []).length < 3) return null
  return g + ext
}

/** fnmatch-style: * any run, ? one character, [..] a set (as the server matches a glob rule). */
export function globMatch(glob: string, s: string): boolean {
  let re = ''
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i]
    if (c === '*') re += '.*'
    else if (c === '?') re += '.'
    else if (c === '[') {
      const j = glob.indexOf(']', i + 2)
      if (j < 0) re += '\\['
      else {
        re += `[${glob.slice(i + 1, j).replace(/\\/g, '\\\\')}]`
        i = j
      }
    } else re += c.replace(/[.+^${}()|\\/]/g, '\\$&')
  }
  return new RegExp(`^${re}$`, 's').test(s)
}

/** The library and folder in a group key ("kind|field|library id|folder"). */
export function groupPlace(key: string): { library: string; folder: string } {
  const parts = key.split('|')
  return { library: parts[2] ?? '', folder: parts.slice(3).join('|') }
}
