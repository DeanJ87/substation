// The sky survey behind the dome (spec 015 amendment, 2026-10-15): every point of the dome shows the patch of sky
// that stood there at the slider's time, from an all-sky image (DSS2 colour or Mellinger), faintly, so the tracks
// sit on the stars and nebulae they were aimed at. Seen from outside (2026-10-22) the sky is painted on the far
// wall; the near shell carries only a ghost of it, so it never hides what lies behind.
import { useEffect, useRef, useState } from 'react'
import { type View, R, siderealDeg, surveyPixel, toEquatorial, unproject } from './projection'
import s from './sky.module.css'

export type Survey = 'dss' | 'mellinger' | 'off'
const GAIN: Record<Exclude<Survey, 'off'>, number> = { dss: 2.6, mellinger: 1.3 }
/** How strongly the near shell shows the sky, against 1 on the far wall. */
export const NEAR = 0.2
const WIDTH = 2048 // the survey is sampled at this width: about 10′ a pixel, plenty for a whole dome

type Pixels = { data: Uint8ClampedArray; w: number; h: number }
const loaded = new Map<string, Promise<Pixels>>()

function load(name: string): Promise<Pixels> {
  let p = loaded.get(name)
  if (!p) {
    p = new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => {
        const h = WIDTH / 2
        const c = document.createElement('canvas')
        c.width = WIDTH
        c.height = h
        const g = c.getContext('2d', { willReadFrequently: true })
        if (!g) return reject(new Error('no canvas'))
        g.drawImage(img, 0, 0, WIDTH, h)
        resolve({ data: g.getImageData(0, 0, WIDTH, h).data, w: WIDTH, h })
      }
      img.onerror = () => reject(new Error('survey unavailable'))
      img.src = `/api/v1/sky/survey/${name}`
    })
    p.catch(() => loaded.delete(name))
    loaded.set(name, p)
  }
  return p
}

/** Paint the dome: for each pixel, the sky at that altitude and azimuth at time `t`. */
export function paint(
  out: ImageData,
  sky: Pixels,
  box: { x: number; y: number; w: number; h: number },
  view: View,
  lat: number,
  lon: number,
  t: number,
  gain: number,
) {
  const lst = siderealDeg(t, lon)
  const { width: cw, height: ch, data } = out
  for (let py = 0; py < ch; py++) {
    const y = box.y + ((py + 0.5) / ch) * box.h
    for (let px = 0; px < cw; px++) {
      const x = box.x + ((px + 0.5) / cw) * box.w
      const i = (py * cw + px) * 4
      let r = 0
      let g = 0
      let b = 0
      let a = 0
      // the far wall first, then the near shell's ghost over it ("over" compositing, premultiplied)
      for (const [side, weight] of [
        ['back', 1],
        ['front', NEAR],
      ] as const) {
        const p = unproject(x, y, view, R, side)
        if (!p) continue
        const { ra, dec } = toEquatorial(p.alt, p.az, lat, lst)
        const [sx, sy] = surveyPixel(ra, dec, sky.w, sky.h)
        const j = (sy * sky.w + sx) * 4
        // fades in from the horizon, where the real sky is murky anyway
        const k = weight * Math.min(1, 0.35 + p.alt / 40)
        r = sky.data[j] * gain * k + r * (1 - k)
        g = sky.data[j + 1] * gain * k + g * (1 - k)
        b = sky.data[j + 2] * gain * k + b * (1 - k)
        a = k + a * (1 - k)
      }
      data[i] = a ? r / a : 0
      data[i + 1] = a ? g / a : 0
      data[i + 2] = a ? b / a : 0
      data[i + 3] = 255 * a
    }
  }
}

export function SkySurvey({
  survey,
  box,
  view,
  fast = false,
  lat,
  lon,
  t,
}: {
  survey: Survey
  box: { x: number; y: number; w: number; h: number }
  view: View
  fast?: boolean
  lat: number
  lon: number
  t: number
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [pixels, setPixels] = useState<Pixels | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (survey === 'off') return
    let live = true
    load(survey).then(
      (p) => live && (setPixels(p), setFailed(false)),
      () => live && setFailed(true),
    )
    return () => {
      live = false
    }
  }, [survey])
  useEffect(() => {
    const c = ref.current
    if (!c || !pixels || survey === 'off') return
    const raf = requestAnimationFrame(() => {
      // half resolution while the dome is being turned, so it keeps up; full when it stops
      const scale = fast ? 0.5 : Math.min(window.devicePixelRatio || 1, 1.5)
      const w = Math.max(1, Math.round(c.clientWidth * scale))
      const h = Math.max(1, Math.round((w * box.h) / box.w))
      if (c.width !== w || c.height !== h) {
        c.width = w
        c.height = h
      }
      const g = c.getContext('2d')
      if (!g) return
      const img = g.createImageData(w, h)
      paint(img, pixels, box, view, lat, lon, t, GAIN[survey])
      g.putImageData(img, 0, 0)
    })
    return () => cancelAnimationFrame(raf)
  }, [pixels, survey, box, view, fast, lat, lon, t])
  if (survey === 'off') return null
  return (
    <>
      <canvas ref={ref} className={s.survey} aria-hidden="true" />
      {failed && <p className={s.surveyNote}>The sky survey couldn’t be loaded.</p>}
    </>
  )
}

export const CREDIT: Record<Exclude<Survey, 'off'>, string> = {
  dss: 'Sky: DSS2 colour (STScI/NASA, via CDS)',
  mellinger: 'Sky: Mellinger all-sky mosaic (via CDS)',
}
