// Finished projects (spec 020): where they come from, and the processing steps a new one starts with.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { api, unwrap } from '../../api/client'
import { toast } from '../../components/Toasts'
import { StepList } from '../finished/StepList'
import { useSettings } from './draft'
import { SettingsSection } from './SettingsSection'

export function FinishedDefaults() {
  const q = useSettings()
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: async (steps: string[]) =>
      unwrap(await api.PUT('/finished/defaults/processing', { body: { steps } })),
    onSuccess: (steps) => {
      qc.setQueryData(['settings'], (old) => old && { ...(old as object), default_processing: steps })
      toast('Default processing steps saved.')
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: ['settings'] }),
    meta: { failed: "Couldn't save the default processing steps" },
  })
  const d = q.data
  if (!d) return null
  return (
    <SettingsSection id="finished" title="Finished projects">
      <p className="muted">
        <Link to="/finished">Finished</Link> lists the project folders in a library with the Completed role
        (set under Folders above). A new finished project starts with these processing steps; you can change
        them for each project.
      </p>
      <StepList
        name="Default processing steps"
        steps={d.default_processing ?? []}
        disabled={!d.can_edit}
        saving={save.isPending}
        onSave={(steps) => save.mutate(steps)}
      />
    </SettingsSection>
  )
}
