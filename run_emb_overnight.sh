#!/bin/bash
cd ~/obraz-app
for i in $(seq 1 30); do
  .venv/bin/python -m scripts.build_embeddings >> emb.log 2>&1
  if tail -3 emb.log | grep -q "готово:"; then
    echo "WATCHDOG: обработка завершена (попытка $i)" >> emb.log
    break
  fi
  echo "WATCHDOG: перезапуск после сбоя (попытка $i), пауза 15с" >> emb.log
  sleep 15
done
