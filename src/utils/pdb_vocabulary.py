"""Local PDB deposition classification vocabulary, reviewed 2026-10-02.

See VOCABULARY_URL for the official dictionary item.
The dictionary's deposition enumeration is distinct from free-text keywords.
"""

import re
from typing import Any

from .checks import CheckResult, any_pass_status, normalize_text, plain_text


VOCABULARY_URL = (
    "https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/"
    "Items/_struct_keywords.pdbx_keywords.html"
)
CLASSIFICATIONS = frozenset(normalize_text(term) for term in (
    "ALLERGEN", "ANTIBIOTIC", "ANTIFREEZE PROTEIN", "ANTIFUNGAL PROTEIN",
    "ANTIMICROBIAL PROTEIN", "ANTITOXIN", "ANTITUMOR PROTEIN", "ANTIVIRAL PROTEIN",
    "APOPTOSIS", "ATTRACTANT", "BIOSYNTHETIC PROTEIN", "BLOOD CLOTTING",
    "CARBOHYDRATE", "CELL ADHESION", "CELL CYCLE", "CELL INVASION", "CHAPERONE",
    "CHOLINE-BINDING PROTEIN", "CIRCADIAN CLOCK PROTEIN", "CONTRACTILE PROTEIN",
    "CYTOKINE", "CYTOSOLIC PROTEIN", "DE NOVO PROTEIN", "DNA", "DNA BINDING PROTEIN",
    "DNA-RNA HYBRID", "ELECTRON TRANSPORT", "ENDOCYTOSIS", "EXOCYTOSIS",
    "FLAVOPROTEIN", "FLUORESCENT PROTEIN", "GENE REGULATION", "HORMONE", "HYDROLASE",
    "IMMUNE SYSTEM", "IMMUNOSUPPRESSANT", "ISOMERASE", "LIGASE", "LIPID BINDING PROTEIN",
    "LIPID TRANSPORT", "LUMINESCENT PROTEIN", "LYASE", "MEMBRANE PROTEIN",
    "METAL BINDING PROTEIN", "METAL TRANSPORT", "MOTOR PROTEIN", "NEUROPEPTIDE",
    "NUCLEAR PROTEIN", "ONCOPROTEIN", "OXIDOREDUCTASE", "OXYGEN BINDING",
    "OXYGEN STORAGE", "OXYGEN TRANSPORT", "PEPTIDE BINDING PROTEIN", "PHOTOSYNTHESIS",
    "PLANT PROTEIN", "PROTEIN BINDING", "PROTEIN FIBRIL", "PROTEIN TRANSPORT",
    "PROTON TRANSPORT", "RECOMBINATION", "REPLICATION", "RIBOSOMAL PROTEIN",
    "RIBOSOME", "RNA", "RNA BINDING PROTEIN", "SIGNALING PROTEIN", "SPLICING",
    "STRUCTURAL GENOMICS", "STRUCTURAL PROTEIN", "SUGAR BINDING PROTEIN",
    "SURFACTANT PROTEIN", "TOXIN", "TRANSCRIPTION", "TRANSFERASE", "TRANSLATION",
    "TRANSLOCASE", "TRANSPORT PROTEIN", "UNKNOWN FUNCTION", "VIRAL PROTEIN", "VIRUS",
    "VIRUS LIKE PARTICLE",
))


def classification_evidence(value: Any) -> CheckResult:
    """Check each component of composite headers such as DNA/RNA.

    Preserve unmatched historical or specialized terms as UNSURE: this snapshot
    cannot establish that they were invalid in another dictionary revision.
    At least one verified component suffices for M5's existing criterion.
    """
    text = plain_text(value)
    terms = [normalize_text(term) for term in re.split(r"[/,]", text)]
    terms = [term for term in terms if term]
    assignments = [{
        "term": term,
        "status": "PASS" if term in CLASSIFICATIONS else "UNSURE",
    } for term in terms]
    return {
        "value": value,
        "vocabulary": "PDBx/mmCIF deposition classification",
        "sourceUrl": VOCABULARY_URL,
        "reviewedAt": "2026-10-02",
        "status": any_pass_status(item["status"] for item in assignments),
        "message": (
            "Membership in the documented deposition enumeration; "
            "no functional accuracy claim."
        ),
        "assignments": assignments,
    }
