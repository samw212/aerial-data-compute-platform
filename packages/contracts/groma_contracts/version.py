"""Version identifiers that end up in tender documents.

CONTRACTS_VERSION changes when a data shape changes in a way that a stored row or
a generated TypeScript type would notice. It is not the kernel version: that lives
in groma_coverage.kernel and is recorded per coverage run.
"""

from typing import Final

CONTRACTS_VERSION: Final[str] = "0.2.0"
