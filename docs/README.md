# Documents

| File | What it is |
| ---- | ---------- |
| `build-spec.md` | Milestones, schemas, API surface, test specifications. §-referenced everywhere. |
| `explained.md` | The same design from first principles. Read this when a concept is unfamiliar. |
| `design.md` | **Not supplied.** See below. |
| `STATUS.md` | What is built, what is stubbed, and where the next session starts. |
| `pdf/` | The source PDFs the markdown was derived from. Authoritative on any disagreement. |

`build-spec.md` and `explained.md` are text extractions of `pdf/groma-build-spec.pdf` and
`pdf/groma-explained.pdf`. The wording is verbatim; only the heading structure and code
fencing were reconstructed, because the PDFs carry no structural markup. Tables from the
PDFs survive as fixed-width text inside fenced blocks rather than as markdown tables.
Where a number matters, check it against the PDF.

`CLAUDE.md` at the repository root is a hand-transcription of `pdf/CLAUDE.pdf`, with the
"Current milestone" section updated as milestones land.

## design.md is missing

Both supplied documents reference `docs/design.md` — "the compressed engineering
design" — as one of three companion documents. It was not among the files supplied to
this repository, so it does not exist here. Nothing in M0 or M1 depended on it: the build
spec is self-contained on contracts (§4), the kernel (§6) and tests (§6.6). Add it when
available; the cross-references in `CLAUDE.md` and `build-spec.md` already point at the
right path.
