// A menu button's keyboard (WAI-ARIA menu button pattern): opening puts focus on the first item, the arrow keys,
// Home and End move between items, Escape closes and gives focus back to the button, Tab closes.
import { useEffect, useRef, type KeyboardEvent } from 'react'

export function useMenu(open: boolean, setOpen: (open: boolean) => void) {
  const button = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLElement>(null)
  const items = (): HTMLElement[] =>
    menu.current ? Array.from(menu.current.querySelectorAll<HTMLElement>('[role="menuitem"]')) : []
  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()
  }, [open])
  const onKeyDown = (e: KeyboardEvent) => {
    const all = items()
    const i = all.indexOf(document.activeElement as HTMLElement)
    const go = (n: number) => {
      e.preventDefault()
      all[(n + all.length) % all.length]?.focus()
    }
    if (e.key === 'ArrowDown') go(i + 1)
    else if (e.key === 'ArrowUp') go(i - 1)
    else if (e.key === 'Home') go(0)
    else if (e.key === 'End') go(all.length - 1)
    else if (e.key === 'Escape') {
      e.preventDefault()
      e.stopPropagation()
      setOpen(false)
      button.current?.focus()
    } else if (e.key === 'Tab') setOpen(false)
  }
  return { button, menu, onKeyDown } as const
}
