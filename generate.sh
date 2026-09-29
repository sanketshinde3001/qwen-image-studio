#!/bin/bash
# Usage: ./generate.sh "prompt" [width] [height] [steps] [seed]
#        TURBO=1 ./generate.sh "prompt"   (4-step LoRA, steps and CFG are fixed)
cd "$(dirname "$0")"
P="${1:-a cute orange kitten sitting on a stack of books, soft window light, photorealistic}"
W="${2:-1024}"; H="${3:-1024}"; S="${4:-20}"; SEED="${5:-42}"
OUT="outputs/$(date +%Y%m%d-%H%M%S)_gen_${W}x${H}_s${SEED}.png"
EXTRA=(--steps "$S" --cfg-scale 6.0)
if [ "$TURBO" = 1 ]; then
  P="<lora:fun-acc-4step:1>$P"
  EXTRA=(--steps 4 --cfg-scale 1.0 --lora-model-dir models/loras
         --sigmas "1.0,0.9169867038726807,0.7861579060554504,0.5494909882545471,0.0")
fi
/usr/bin/time -l bin/sd-cli \
  --diffusion-model models/qwen-image-2.1-Q4_K_M.gguf \
  --llm            models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  --vae            models/qwen_image_2.1_vae_bf16.safetensors \
  -p "$P" "${EXTRA[@]}" --sampling-method euler \
  -W "$W" -H "$H" --seed "$SEED" --diffusion-fa --vae-tiling \
  --model-args qwen_image_2_1_prefix_cache_type=q8_0 \
  -o "$OUT" 2>&1 | tee "logs/gen-$(date +%s).log"
echo "Saved: $OUT"
