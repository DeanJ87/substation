// The close look's zoom maths (2026-10-15), apart from the component so it can be checked on its own.

type Size = { w: number; h: number }

/** The most the close look zooms in: 800%. */
export const MAX_ZOOM = 8

/** The scale at which the whole image fits the window; never above 100%, and 100% until both sizes are known. */
export function fitScale(box: Size | null, image: Size | null): number {
  return box && image ? Math.min(box.w / image.w, box.h / image.h, 1) : 1
}

/** A requested scale kept between "fit" (or 100%, for an image smaller than the window) and the maximum. */
export function clampZoom(next: number, fit: number): number {
  return Math.min(MAX_ZOOM, Math.max(Math.min(fit, 1), next))
}

/** The scroll offset that keeps the image point under the pointer (`at`, from the window's edge) where it is when
 * the scale goes from `from` to `to`. */
export function anchoredScroll(scroll: number, at: number, from: number, to: number): number {
  return ((scroll + at) / from) * to - at
}
