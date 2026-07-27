# Source Metadata Standard

Every silver and gold table should preserve source/context fields where possible.

## Required source metadata fields

| Field | Meaning |
|---|---|
| `source_id` | Internal ID linking the row back to `source_manifest.csv`. |
| `source_name` | Human-readable source name. |
| `source_url` | Direct URL or source description. |
| `date_accessed` | Date the source was accessed or recorded. |
| `ingested_at` | Timestamp when the data entered the platform. |
| `verification_status` | Whether the source/row is verified, partial, needs verification, or no clear match found. |
| `source_caveat` | Warning about how the source should be interpreted. |
| `manual_or_automated` | Whether the source was collected manually, semi-automated, or automated. |

## Why this matters

Spartan Judicial should be able to trace every candidate dossier field back to a source. The platform should not only show data; it should show whether the data is verified, incomplete, manually checked, or caveated.