# biosensor_samples

This folder holds the curated samples for the /biosensor gallery.

## What's here

Each subfolder is one sample. The metadata.json files are already
filled in. You need to ADD the electrochemistry trace files.

## What you add

Into each sample folder, place the raw CHI660E .txt exports, renamed:

  ca.txt    <- Chronoamperometry
  cv.txt    <- Cyclic Voltammetry
  ocp.txt   <- Open Circuit Potential   (Phase II samples only)
  dpv.txt   <- Differential Pulse Voltammetry  (Phase II samples only)

Phase I samples (healthy_p1_trial4, healthy_p1_trial5,
unhealthy_p1_trial7) only have ca.txt and cv.txt — that is expected,
per the study design. Do not fabricate ocp/dpv for them.

## Rules

- Keep the raw exported .txt format. Do NOT open and re-save in Excel.
- Just copy the file and rename it. Renaming does not change contents.
- Lowercase filenames exactly as above.

## If dropping Phase I

If you decide to ship Phase II only, delete the three p1 folders.
