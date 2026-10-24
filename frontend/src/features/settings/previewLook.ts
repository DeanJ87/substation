// The preview look's maths, as the server draws sub previews (backend/apps/processing/previews.py, 003 amendment
// 2026-10-24), for the small example in Settings: a synthetic clear sub and a cloudy one drawn with the chosen look.
export type Look = { mode: 'session' | 'sub'; black_point: number; background: number }
export type Params = [lo: number, midtones: number, span: number]

const SHADOW_SIGMAS = 2.8

function percentile(sorted: Float32Array, p: number): number {
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round((p / 100) * (sorted.length - 1))))
  return sorted[i]
}

/** (black level, midtones balance, range) for one frame: the sky at `background` grey with the usual clip, the
 * black point then moved by `blackPoint` noise sigmas. */
export function stretchParams(data: Float32Array, blackPoint = 0, background = 0.25): Params {
  const sorted = Float32Array.from(data).sort()
  const lo = percentile(sorted, 0.01)
  const hi = percentile(sorted, 99.999)
  const span = Math.max(hi - lo, 1e-9)
  const norm = sorted.map((v) => Math.min(1, Math.max(0, (v - lo) / span)))
  const med = percentile(norm, 50)
  const dev = norm.map((v) => Math.abs(v - med)).sort()
  const mad = percentile(dev, 50) * 1.4826
  const base = Math.max(0, med - SHADOW_SIGMAS * mad)
  const m = (med - base) / Math.max(1e-9, 1 - base)
  const t = Math.min(0.45, Math.max(0.05, background))
  const midtones = m > 0 ? ((t - 1) * m) / ((2 * t - 1) * m - t) : 0.5
  const shadows = Math.max(0, med - Math.max(0.25, SHADOW_SIGMAS - blackPoint) * mad)
  return [lo + shadows * span, midtones, span * (1 - shadows)]
}

/** One stretch for several frames: the median of each parameter. */
export function sharedParams(all: Params[]): Params {
  const med = (xs: number[]) => {
    const s = [...xs].sort((a, b) => a - b)
    const n = s.length
    return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2
  }
  return [0, 1, 2].map((k) => med(all.map((p) => p[k]))) as Params
}

/** 8-bit grey values of `data` drawn with `params`. */
export function draw(data: Float32Array, [lo, m, span]: Params): Uint8ClampedArray {
  const out = new Uint8ClampedArray(data.length)
  for (let i = 0; i < data.length; i++) {
    const x = Math.min(1, Math.max(0, (data[i] - lo) / Math.max(span, 1e-9)))
    out[i] = Math.round((((m - 1) * x) / ((2 * m - 1) * x - m)) * 255)
  }
  return out
}

export const SAMPLE_W = 180
export const SAMPLE_H = 110

/** A synthetic sub: sky with noise, a faint glow and a few stars; `transparency` < 1 is cloud (dimmer, flatter). */
export function sampleSub(transparency: number, seed = 7): Float32Array {
  let x = seed
  const rand = () => {
    x = (x * 1103515245 + 12345) % 2147483648
    return x / 2147483648
  }
  const gauss = () => Math.sqrt(-2 * Math.log(rand() + 1e-12)) * Math.cos(2 * Math.PI * rand())
  const stars = Array.from({ length: 14 }, () => [rand() * SAMPLE_W, rand() * SAMPLE_H, 0.05 + rand() * 0.6])
  const a = new Float32Array(SAMPLE_W * SAMPLE_H)
  for (let r = 0; r < SAMPLE_H; r++)
    for (let c = 0; c < SAMPLE_W; c++) {
      const glow = 0.02 * Math.exp(-(((c - 110) / 40) ** 2 + ((r - 50) / 30) ** 2))
      let v = 0.1 + glow + 0.006 * gauss()
      for (const [sx, sy, b] of stars) v += b * Math.exp(-((c - sx) ** 2 + (r - sy) ** 2) / 2.2)
      a[r * SAMPLE_W + c] = v * transparency + (1 - transparency) * 0.06 // cloud: less signal, some scattered light
    }
  return a
}

/** The example's two frames, drawn as the server would with this look. */
export function drawPair(look: Look): [Uint8ClampedArray, Uint8ClampedArray] {
  const clear = sampleSub(1)
  const cloudy = sampleSub(0.45)
  const own = [clear, cloudy].map((d) => stretchParams(d, look.black_point, look.background))
  const shared = sharedParams([own[0], own[0], own[0], own[1]]) // a session of mostly clear subs
  return [
    draw(clear, look.mode === 'session' ? shared : own[0]),
    draw(cloudy, look.mode === 'session' ? shared : own[1]),
  ]
}
