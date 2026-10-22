// Putting things away (006-DR-40): five verbs, each with one meaning, worded the same everywhere. Only Archive and
// the Bin ever touch your files; Delete removes a record (a stack or combined master is the exception: it's a file).

export type Verb = 'done' | 'archive' | 'bin' | 'unlink' | 'delete'

export type VerbWords = {
  /** The menu item or button. */
  label: string
  /** The way back. */
  restore: string
  /** What happens to the files, in one sentence. */
  files: string
  /** How to undo it, in one sentence. */
  undo: string
}

export const VERBS: Record<Verb, VerbWords> = {
  done: {
    label: 'Mark done',
    restore: 'Reopen',
    files: "Your files aren't touched.",
    undo: 'Reopen it from the project menu.',
  },
  archive: {
    label: 'Archive files',
    restore: 'Bring back files',
    files: 'Its files move to the archive library.',
    undo: 'Bring them back from the collection menu.',
  },
  bin: {
    label: 'Bin',
    restore: 'Restore',
    files: 'The files go to the Bin and are deleted after 30 days.',
    undo: 'Restore them from the Bin until then.',
  },
  unlink: {
    label: 'Unlink',
    restore: 'Link again',
    files: "Your files aren't touched.",
    undo: 'Link it again, or Undo from Activity for 30 days.',
  },
  delete: {
    label: 'Delete',
    restore: 'Undo',
    files: "Your files aren't touched.",
    undo: 'Undo from Activity for 30 days.',
  },
}

/** A stack or combined master is its own output file: deleting it removes the file for good. */
export const FILE_DELETED = "File deleted now; can't be undone."

/** "Deleted collection M31" / "Restored collection M31." — the same words the server writes in Activity. */
export const deletedText = (what: 'collection' | 'project', name: string) => `Deleted ${what} ${name}`

/** The Library's Show filter and the one label set for where a collection's files are (Active, Archived, Partly
 * archived, Worth archiving). */
export const WHERE_LABEL: Record<string, string> = {
  active: 'Active',
  archive: 'Archived',
  both: 'Partly archived',
  suggested: 'Worth archiving',
}
