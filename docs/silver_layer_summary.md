# Silver Layer Summary

## Purpose

The silver layer contains cleaned and standardized data produced from the raw bronze files.

The first completed silver output is:

`data/silver/target_3_campaign_dossier_clean.csv`

This file is the cleaned version of the raw target three-campaign dossier.

## Input

Bronze input:

`data/bronze/target_3_campaign_dossier_raw.csv`

## Output

Silver output:

`data/silver/target_3_campaign_dossier_clean.csv`

## Cleaning performed

The transformation script cleaned the target dossier by:

- removing empty rows and empty columns,
- stripping leading and trailing whitespace,
- preserving identifier fields such as `filer_id` and `bar_number` as strings,
- removing commas from money fields,
- converting contribution and expenditure fields into numeric values,
- standardizing status values such as `No`, `Yes`, and `High`,
- adding source metadata fields,
- adding an ingestion timestamp,
- adding a source caveat.

## Validation result

The cleaned target dossier passed schema validation for all three target campaigns:

- Joe Radler — passed
- Paul Sullivan — passed
- Tami Pierce — passed

## Why this matters

This confirms that the project can take a messy campaign dossier file and turn it into a standardized, validated dataset.

This is the foundation for producing gold campaign-ready outputs such as candidate dossiers, readiness scores, source-quality summaries, and risk signals.