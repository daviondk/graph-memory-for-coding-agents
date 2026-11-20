from pathlib import Path
def ordered_pages(directory):
    # Put the two main experiments first, and keep each downstream test beside its corresponding retrieval experiment.
    order=["01-summary","02-design","05b-address","05c-transfer","05e-address-model","05d-next-action","05-writer",
           "03b-budget","03c-math","03c-online","03d-transfer","06d-depth","03-retrieval","04-neural",
           "06-reader-design","06a-evidence","06b-gate","06c-draft","08-crosscode","07-related","08b-prior","09-next"]
    files={p.stem:p for p in Path(directory).glob("*.md")}
    return [files[n] for n in order if n in files]+[files[n] for n in sorted(set(files)-set(order))]

