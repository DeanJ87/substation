// A collection's name read as its parts: "NGC 7635 - Bubble Nebula" is the Bubble Nebula, catalogued as NGC 7635.
// The title shows the common name with the designation beside it, so the subtitle needn't repeat either.

const key = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')

export function nameParts(name: string): { title: string; designation: string } {
  const i = name.indexOf(' - ')
  if (i > 0) return { title: name.slice(i + 3).trim(), designation: name.slice(0, i).trim() }
  return { title: name, designation: '' }
}

/** Other object names in the collection that the title doesn't already say ("NGC 6992" in the Veil). */
export function otherObjects(name: string, objects: string): string[] {
  const { title, designation } = nameParts(name)
  const known = [title, designation].map(key).filter(Boolean)
  return objects
    .split(' · ')
    .map((o) => o.trim())
    .filter((o) => {
      const k = key(o)
      return k && !known.some((n) => k === n || k.includes(n) || n.includes(k))
    })
}

/** "Cassiopeia · 2 datasets · also NGC 6992" */
export function collectionFacts(c: {
  name: string
  objects: string
  constellation?: string | null
  datasets: number
}): string {
  const also = otherObjects(c.name, c.objects)
  return [
    c.constellation,
    `${c.datasets} dataset${c.datasets === 1 ? '' : 's'}`,
    also.length ? `also ${also.join(', ')}` : '',
  ]
    .filter(Boolean)
    .join(' · ')
}
