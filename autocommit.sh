#!/bin/bash
DIR="/Users/haotian/Documents/Stock"
cd "$DIR"
echo "[autocommit] 监控 $DIR ..."
fswatch -0 -e "data/" -e "output/" -e ".git/" -e "*.pyc" -e ".DS_Store" "$DIR" | while read -d "" file; do
  sleep 5
  git add -A
  if ! git diff --cached --quiet; then
    git commit -m "auto: $(date '+%m-%d %H:%M') - $(basename "$file")"
    echo "[autocommit] $(date '+%H:%M:%S') committed"
  fi
done
