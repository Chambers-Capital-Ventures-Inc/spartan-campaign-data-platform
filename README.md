<img width="6895" height="8191" alt="Data Validation Pipeline-2026-08-16-165748" src="https://github.com/user-attachments/assets/8aa0dfd7-0f1f-421b-9298-74d6ceb56250" />
# Spartan Judicial Campaign Data Platform

## Overview

This project is a campaign data lakehouse, validation, and evaluation prototype for Spartan Judicial.

It is designed to collect, clean, validate, evaluate, and serve campaign data for judicial campaigns, starting with three target races:

- Joe Radler — 311th Family Court
- Paul Sullivan — 113th Civil Court
- Tami Pierce — 180th Criminal Court

## Project Goal

The goal is to build a repeatable campaign data infrastructure system, not just a dashboard.

The system will organize messy public and campaign data into bronze, silver, and gold layers, run validation and data quality checks, generate readiness/risk signals, and serve campaign-ready candidate profiles.

## Current Status

Phase 0: Scope, onboarding, and repo setup.

## Planned Architecture

1. Ingestion layer
2. Bronze/raw data layer
3. Silver/cleaned data layer
4. Gold/campaign-ready data layer
5. Validation and evaluation layer
6. Dashboard/serving layer

## Folder Structure

- `data/bronze`: raw source files
- `data/silver`: cleaned standardized files
- `data/gold`: campaign-ready outputs
- `src/ingestion`: ingestion scripts
- `src/schemas`: Pydantic schemas
- `src/validation`: data validation checks
- `src/transformations`: transformation scripts
- `src/evaluation`: readiness/risk-signal logic
- `app/streamlit`: dashboard code
- `docs`: project documentation
- `onboarding`: teammate onboarding materials
- `tests`: automated tests
- `reports`: generated reports

## Final Deliverables

- Working data pipeline prototype
- Bronze/silver/gold data layers
- Validation and quality checks
- Candidate dossier outputs
- Campaign readiness evaluation
- Streamlit dashboard
- Architecture documentation
- Final evaluation report


<img width="6895" height="8191" alt="Data Validation Pipeline-2026-08-16-165748" src="https://github.com/user-attachments/assets/8cf8286e-c668-44be-99ca-30af113b4e22" />
