# Legacy M1–M9 evaluator

This documents the previous generic contract and the shared evaluator retained
by the PDB adapter. Zenodo, Dryad and Figshare now use G01–G10 instead.

Paths refer to the original JSON response. `[]` projects a field from every list item.
The repository tables below are field catalogs, not one-check-per-row lists.
Matching original presence rules are replaced; rules outside M1–M9 are preserved.

| Group | Implemented checks | Regular points | Bonus points |
| --- | --- | --- | --- |
| M1 identifiers | Record, dataset and specific-version identifier presence, recognized syntax and resolver path | 2 | 2.5 |
| M2 title | Nonempty text; obvious literal placeholders/templates | 2 | — |
| M3 description | Nonempty HTML text; warning when identical to the normalized title | 1 | — |
| M4 keywords | At least one nonempty normalized term; duplicate warning | 1 | — |
| M5 subjects | At least one category name/code with vocabulary and verified membership | 1 | — |
| M6 creators | At least one named person/group; valid ORCID and affiliation for every creator; resolved ORCID surname comparison | 1 | 2 |
| M7 organizations | Named/identified publisher, affiliation or repository; separate ROR validation | 1 | — |
| M8 type | Nonempty type; separate Dataset / other resource / file-format classification | 1 | — |
| M9 dates | Nonempty lifecycle dates, recognized formats, order of comparable events | 2 | — |

New results include `group`, `testId`, `kind`, `points` (earned) and `maxPoints`.
The summary separates `score/maxScore` (12 regular points) from `bonusScore/maxBonusScore`
(4.5 bonus points), and counts `WARNING` and `UNSURE` separately. Only `PASS` earns points.
Warnings, diagnostics, legacy presence rules and aggregator checks do not affect these scores.

No NLP/LLM checks run. Description content components (M3 Test-02), keyword relevance
(M4 Test-03), authentication of ORCID ownership and semantic organization-name matching are omitted.
M2 Test-02 fails an empty title or recognized literal template; otherwise it is `UNSURE`.
Absence of a template cannot establish informativeness, so its one point remains unawarded.
An explicitly unmapped PDB description or generic resource type produces `UNSURE`
and earns no points. The 12-point denominator stays unchanged; this is evidence
available through the selected endpoint, not an assessment of structural accuracy.

**Identifiers**

- Generic repository record IDs use `id`, validated as positive integers in the local scheme.
  PDB uses `rcsb_id` with legacy or extended accession syntax.
- Dataset IDs use Zenodo `conceptdoi` (fallback `doi`), Dryad `identifier`, or Figshare `doi`
  with a standard Figshare `.vN` suffix removed.
  PDB uses `database_2[].pdbx_DOI` from the row whose `database_id` is `PDB`,
  preserving the selected array index in evidence and checking entry identity.
- Specific-version IDs use Zenodo `doi`, a standard Figshare `.vN` DOI, or explicit `versionIdentifier`.
  A version number/label alone is not an identifier; the original `Version` checks remain.
  PDB major/minor revisions are retained as presence checks, not promoted to version identifiers.
- Supported syntax: DOI, Handle, ARK, HTTP(S) URL, UUID and URN. DOI, Handle, ARK and URLs
  have resolver paths. Arbitrary URNs/UUIDs have no assumed resolver and remain `UNSURE` for resolution.
  Record IDs use repository API URLs; Dryad uses a supplied `_links.self.href` when available.
- Resolver verification follows up to five redirects and closes the final response without reading
  its body. If a resolver exposes no resource target, resolution remains `UNSURE`.

**Text and controlled identifiers**

Title/description presence requires text, not numbers/containers. HTML is parsed for descriptions.
Keywords use Unicode NFKC, case folding and whitespace normalization; empty/nontext terms are
ignored, one nonempty term suffices, and duplicates produce a zero-point warning.
PDB keywords are split on commas before normalization; their original text remains visible.
Creators can be groups or people with a single name. Every creator needs a valid ORCID and an
affiliation for those bonuses; empty lists earn neither bonus. ORCID validation includes the
[format and MOD 11-2 checksum](https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier).
Scalar affiliations and structured `affiliations[]` are accepted.

M6 `Test-02-01` is a separate zero-point diagnostic. Each valid supplied ORCID is resolved through
the [ORCID Public API](https://info.orcid.org/documentation/api-tutorials/api-tutorial-read-data-on-a-record/)
at `https://pub.orcid.org/v3.0/{orcid}/person`, and its public `name.family-name.value` is compared
with the creator's metadata surname. Dryad uses `lastName`; comma-separated names use the part
before the comma (including Zenodo and PDB). For unstructured given-name-first names such as
Figshare `full_name`, comparison uses the trailing whole words corresponding to the ORCID family
name, preserving compound surnames. Comparison normalizes Unicode NFKC, case and whitespace;
diacritics are retained and given names/initials are not compared. Per-author evidence retains the
original name and ORCID, both surnames, status and verification URL. Every creator must pass for
the diagnostic to pass. Missing ORCIDs, missing surnames and unavailable/private ORCID names
produce `UNSURE`; invalid identifiers, nonexistent ORCIDs and surname mismatches produce `FAIL`.
A surname match is evidence of metadata consistency; it does not authenticate ORCID ownership.

Dryad `fieldOfScience` and explicitly declared OECD FOS subjects use a local
[OECD FOS 2007 lookup](https://www.oecd-ilibrary.org/mapping-careers-and-mobility-of-doctorate-holders_5kzsnsbph6g5.pdf).
Figshare categories use its [public category list](https://docs.figshare.com/old_docs/api/categories/).
EFO, MeSH and GND identifiers use OLS4, NLM and lobid respectively; unsupported vocabulary
lookups remain `UNSURE`. Organization presence uses actual metadata, not an invented adapter name.
ROR identifiers have format/checksum validation followed by a [ROR v2 lookup](https://ror.readme.io/docs/api-single).
PDB classification terms use a local snapshot of the
[PDBx/mmCIF deposition vocabulary](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_struct_keywords.pdbx_keywords.html).
Composite headers are checked component by component. Unlisted historical terms
remain `UNSURE`; free-text keywords are not used as controlled classifications.
ROR verification and type classification are zero-point diagnostics because no additional weights
were specified. A missing type remains missing, including Dryad responses without this field.

**Dates**

M9 uses `Test-01` for presence, `Test-01-01` for parsing (0.5 points), and `Test-02` for
order (0.5 points), disambiguating the two supplied Test-01 labels. Supported formats are
ISO year/month/day, ISO timestamps with optional timezone, `YYYY/MM/DD` and `DD.MM.YYYY`.
Ambiguous slash formats and invalid calendar dates produce `UNSURE` for parsing.
At least one nonempty lifecycle date satisfies presence; every supplied lifecycle date must parse
for the parsing check to pass. Coverage retains its original presence checks.

Creation ≤ publication and creation ≤ update comparisons use only events of the same scope.
Publication and modification are not automatically ordered: a metadata edit may precede publication or embargo release.
Zenodo record creation/update are compared to each other, not the dataset's publication;
explicit created/issued/updated entries in `metadata.dates` describe the resource instead.
Dryad publication/creation/last-modification and Figshare created/published/modified dates
are resource events. PDB deposition, initial release and latest revision are record events;
article publication and experiment dates do not substitute for them.
Year/month/day precision becomes an interval; overlapping precision,
mixed timezone awareness and missing pairs remain `UNSURE` if order cannot be established.
There is no future-date, current-date or age cutoff, so historical and embargo dates are allowed.

**Availability and unchanged presence checks**

Verification uses up to eight concurrent workers, eight-second request timeouts, at most five
redirects and public HTTP(S) destinations. Each distinct URL is requested once per evaluation.
HTTP 404/410 means a failed lookup; timeouts, rate limits, malformed replies and service
failures mean `UNSURE`. Evidence retains individual assignments and verification/target URLs.
Verification failures preserve local checks. Repository loading errors still produce no checks.

Unchanged presence rules retain their behavior: missing/null/blank values and empty lists/objects
fail, every projected list item must have a value, objects need a nonempty value, and `0`/`false`
count as present. Missing optional fields also fail these legacy rules.

