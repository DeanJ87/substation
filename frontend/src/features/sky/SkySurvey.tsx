// The sky survey behind the dome (spec 015 amendment, 2026-10-15): every point of the dome shows the patch of sky
// that stood there at the slider's time, from an all-sky image (DSS2 colour or Mellinger), faintly, so the tracks
// sit on the stars and nebulae they were aimed at.
import { useEffect, useRef, useState } from 'react'
import { type View, R, siderealDeg, surveyPixel, toEquatorial, unproject } from './projection'
import s from './sky.module.css'

export type Survey = 'dss' | 'mellinger' | 'off'
const GAIN: Record<Exclude<Survey, 'off'>, number> = { dss: 2.6, mellinger: 1.3 }
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
      const p = unproject(x, y, view, R)
      if (!p) {
        data[i + 3] = 0
        continue
      }
      const { ra, dec } = toEquatorial(p.alt, p.az, lat, lst)
      const [sx, sy] = surveyPixel(ra, dec, sky.w, sky.h)
      const j = (sy * sky.w + sx) * 4
      data[i] = sky.data[j] * gain
      data[i + 1] = sky.data[j + 1] * gain
      data[i + 2] = sky.data[j + 2] * gain
      // fades in from the horizon, where the real sky is murky anyway
      data[i + 3] = 255 * Math.min(1, 0.35 + p.alt / 40)
    }
  }
}

export function SkySurvey({
  survey,
  box,
  view,
  lat,
  lon,
  t,
}: {
  survey: Survey
  box: { x: number; y: number; w: number; h: number }
  view: View
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
      const scale = Math.min(window.devicePixelRatio || 1, 1.5)
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
  }, [pixels, survey, box, view, lat, lon, t])
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
