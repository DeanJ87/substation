# Plan: Stacking (POC: stories 1–2)

- `Stack` (dataset or datasets, scope: nights or date range or all, inclusion rule, options, state,
  recipe JSON, who and when, output path, report) and `StackMember` (frame, included, weight, reason).
- `POST /stacks/preview` → count, integration, nights for a scope and rule; `POST /stacks` starts a
  `stack` job in the `siril_heavy` slot; `GET /datasets/{id}/stacks`; `POST /stacks/{id}/rerun`;
  `DELETE /stacks/{id}` (removes only SubStation's output).
- Rules: `default` (effective Accepted and Down-weighted), `accepted`, `graded` (every measured sub),
  `everything` (every sub in scope, including rejected).
- Job: link the members' calibrated FITS into a fresh work folder as a sequence, `register -2pass`,
  `seqapplyreg -framing=current`, `stack r_ rej 3 3 -norm=addscale -weight=wfwhm -32b`; subs that fail
  registration are excluded with "could not match stars". Output to `/data/substation/stacks/<dataset>/`,
  plus an auto-stretched preview PNG and a basic report (stars, FWHM, background noise). Intermediates
  removed afterwards. A sub without a calibrated FITS yet is calibrated first, or the stack waits.
- UI: "Stack" panel on the dataset view (scope by nights, rule, preview, start), stacks list with recipe,
  state, report and preview; re-run and delete.
