# Reconcile

**Reconcile** lists what SubStation couldn't settle on its own. The number in the menu shows how many items
are open.

Items are grouped by what's wrong and by folder, so one answer usually fixes a whole night. Where other files
in the folder agree on a value, SubStation suggests it.

| Item | What to do |
|---|---|
| *Filter missing*, *Exposure missing*, … | Give the value, accept the suggestion, or add a [path pattern](patterns.md) that reads it |
| *Frame type unknown* | Choose the type |
| *Master without gain / offset / temperature* | Give the value: calibration matching needs it. The suggestion comes from the folder name (`-10c`) or from your lights |
| *Missing from disk* | Put the file back and the item clears itself, or accept that it's gone |
| *Rejected in NINA, with no original copy* | For information: a `BAD_` file whose original was never copied. It counts as rejected |
| *More than one master fits* | A multi-image file without an image called `integration`. Its first image is used |

## Your answers stick

A value you give is stored against the **content** of the file, not its path. It applies to every copy,
survives moves and renames, and applies again if the same file turns up later. You can change or undo it from
the sub's detail panel, which shows "set by *you* on *date*" next to the value.

You can also correct values directly: open a sub and choose **Correct** next to a value, or tick several subs
in a dataset and use the bar above the table to set one value for all of them.
