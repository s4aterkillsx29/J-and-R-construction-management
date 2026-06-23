# JRC GitHub Directory Updater

Professional no-console helper for publishing the J&R Construction Manager project directory to GitHub.

## Purpose

This tool is meant to replace the old ZIP-upload workflow. It keeps the project organized as normal GitHub folders/files and adds a safety review step before publishing.

## Start

On Windows, double-click:

```text
Launch_JRC_GitHub_Updater.vbs
```

The launcher opens the Python windowed app without a command prompt.

## Safety workflow

1. Select the J&R Construction Manager project folder.
2. Enter or verify the GitHub repo URL.
3. Keep **Dry Run** enabled first.
4. Scan the directory and review warnings.
5. Write/update `.gitignore`.
6. Run Git Status.
7. Publish only after review.

## Security

The repo `.gitignore` blocks common secrets, private business records, payroll files, tax records, receipts, backups, databases, and customer files. Do not push live private records to a public repository.
