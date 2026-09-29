#!/bin/bash
# Usage: ./edit.sh input.png "edit instruction" [seed] [ref_max_px]
#        TURBO=1 ./edit.sh input.png "instruction"   (4-step LoRA)
# The input is read at ref_max_px (default 768) and the output keeps its aspect ratio.
cd "$(dirname "$0")"
IN="$1"; P="$2"; SEED="${3:-42}"; REF="${4:-768}"
TMP="studio/tmp/cli_ref_$$.png"; mkdir -p studio/tmp
read IW IH < <(sips -g pixelWidth -g pixelHeight "$IN" | awk '/pixel/{print $2}' | xargs)
SHRINK=(); [ "$IW" -gt "$REF" ] || [ "$IH" -gt "$REF" ] && SHRINK=(-Z "$REF")
sips -s format png "${SHRINK[@]}" "$IN" --out "$TMP" >/dev/null
read W H < <(sips -g pixelWidth -g pixelHeight "$TMP" | awk '/pixel/{print $2}' | xargs)
W=$(( (W + 8) / 16 * 16 )); H=$(( (H + 8) / 16 * 16 ))
OUT="outputs/$(date +%Y%m%d-%H%M%S)_edit_${W}x${H}_s${SEED}.png"
EXTRA=(--steps 16 --cfg-scale 6.0)
if [ "$TURBO" = 1 ]; then
  P="<lora:fun-acc-4step:1>$P"
  EXTRA=(--steps 4 --cfg-scale 1.0 --lora-model-dir models/loras
         --sigmas "1.0,0.9169867038726807,0.7861579060554504,0.5494909882545471,0.0")
fi
/usr/bin/time -l bin/sd-cli \
  --diffusion-model models/qwen-image-2.1-Q4_K_M.gguf \
  --llm            models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  --llm_vision     models/mmproj-Qwen3VL-8B-Instruct-F16.gguf \
  --vae            models/qwen_image_2.1_vae_bf16.safetensors \
  -r "$TMP" -p "$P" "${EXTRA[@]}" --sampling-method euler \
  -W "$W" -H "$H" --seed "$SEED" --diffusion-fa --vae-tiling \
  --model-args qwen_image_2_1_prefix_cache_type=q8_0 \
  -o "$OUT" 2>&1 | tee "logs/edit-$(date +%s).log"
rm -f "$TMP"
echo "Saved: $OUT"
