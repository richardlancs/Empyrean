# Person 2 annotation correction for PR 25

User explicitly authorized correcting Person 3 data and sending it to the active combined-training chat.

Imported the original 60 JPEGs unchanged from PR head afeef8f2ecd124cb8e173b8a6823b31d0f2294dc. Redrew phone_2, phone_9 and phone_20 boxes to cover the visible phone and remove ceiling/background. phone_2 reaches the image boundary; its bottom box coordinate is 360.

Use annotation-corrections-p2.json for the preserved 50 training / 10 same-session validation split and image checksums. The ten validation images must not enter training. They are not independent test images. No separate evaluation session has been fabricated.

Original candidate-v1.md and JSON reports are historical: they were generated before these box corrections (including validation image phone_9). Rerun evaluation with corrected refs for current scores. Candidate weights are not supplied by this import. Keep all eight canonical classes when combining datasets.
