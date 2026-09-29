#!/bin/bash
# Fetches the stable-diffusion.cpp binary and all model files (~11.5 GB) into this folder.
# Safe to re-run: finished files are skipped and partial downloads resume.
set -e
cd "$(dirname "$0")"
mkdir -p bin/llama models/loras models/upscalers outputs inputs logs

HF=https://huggingface.co
SD_URL=https://github.com/leejet/stable-diffusion.cpp/releases/download/master-929-3f8527a/sd-master-3f8527a-bin-Darwin-macOS-26.6.2-arm64.zip
LLAMA_URL=https://github.com/ggml-org/llama.cpp/releases/download/b11249/llama-b11249-bin-macos-arm64.tar.gz

fetch() {  # fetch <dest> <url> <expected bytes>
  if [ -f "$1" ] && [ "$(stat -f%z "$1")" = "$3" ]; then echo "ok        $1"; return; fi
  echo "download  $1"
  curl -L --fail -C - -o "$1" "$2"
}

if [ ! -x bin/sd-cli ]; then
  curl -L --fail -o bin/sd.zip "$SD_URL"
  (cd bin && unzip -oq sd.zip && rm sd.zip)
fi

# llama.cpp runs Qwen3-VL for "Describe" and "Suggest edits"
if [ ! -x bin/llama/llama-b11249/llama-mtmd-cli ]; then
  curl -L --fail -o bin/llama.tar.gz "$LLAMA_URL"
  tar -xzf bin/llama.tar.gz -C bin/llama && rm bin/llama.tar.gz
fi

fetch models/qwen-image-2.1-Q4_K_M.gguf           $HF/unsloth/Qwen-Image-2.1-GGUF/resolve/main/qwen-image-2.1-Q4_K_M.gguf 4199565024
fetch models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf $HF/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf 5148699488
fetch models/mmproj-Qwen3VL-8B-Instruct-F16.gguf  $HF/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/mmproj-F16.gguf 1159030336
fetch models/qwen_image_2.1_vae_bf16.safetensors  $HF/unsloth/Qwen-Image-2.1-FP8/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors 675508656
fetch models/loras/fun-acc-4step.safetensors      $HF/eastmoe/Qwen-Image-2.1-Fun-Acc-LoRAs-Comfy/resolve/main/Qwen-Image-2.1-Fun-Acc-4Step-comfyui.safetensors 344600164
fetch models/upscalers/RealESRGAN_x4plus.pth       https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth 67040989
echo "All files ready. Start the studio with ./studio.sh"
