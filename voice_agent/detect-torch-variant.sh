#!/usr/bin/env bash
# detect-torch-variant.sh — imprime la variante de torch según la GPU del host
CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -n1 | tr -d ' ')
case "$CAP" in
  12.*)            echo "cu128" ;;   # Blackwell (RTX 50xx, sm_120)
  7.0|7.5|8.*|9.0) echo "cu121" ;;   # Volta/Turing/Ampere/Ada/Hopper
  *)               echo "cu121" ;;   # fallback conservador
esac