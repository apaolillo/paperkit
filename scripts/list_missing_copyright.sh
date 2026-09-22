#!/bin/sh
# List Python files lacking the copyright header; exit 1 if any.
set -e

copyright_line1="# Copyright (C) 2026 Vrije Universiteit Brussel. All rights reserved."
copyright_line2="# SPDX-License-Identifier: MIT"

missing=$(find src tests scripts -type f -name "*.py" | while IFS= read -r file
do
    header=$(head -n 3 "$file")
    case "$header" in
        *"$copyright_line1"*"$copyright_line2"*)
            ;;
        *)
            echo "$file"
            ;;
    esac
done)

if [ -n "$missing" ]; then
    echo "Files without the copyright header:" >&2
    echo "$missing" >&2
    exit 1
fi
