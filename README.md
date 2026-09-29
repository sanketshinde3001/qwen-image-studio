<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![macOS][macos-shield]][macos-url]
[![Memory][memory-shield]](#how-it-fits-in-16-gb)
[![Python][python-shield]][python-url]
[![Dependencies][deps-shield]](#built-with)
[![Model][model-shield]][model-url]
[![MIT License][license-shield]][license-url]
[![Stars][stars-shield]][stars-url]
[![Views][views-shield]][views-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="#about-the-project">
    <img src="docs/logo.svg" alt="Logo" width="96" height="96">
  </a>

  <h3 align="center">Qwen-Image Studio</h3>

  <p align="center">
    Qwen-Image 2.1 image editing and generation, running locally on a 16 GB Apple Silicon Mac.
    <br />
    <a href="#getting-started"><strong>Get started »</strong></a>
    <br />
    <br />
    <a href="#usage">Usage</a>
    &middot;
    <a href="#benchmarks">Benchmarks</a>
    &middot;
    <a href="#how-it-got-fast">How it got fast</a>
    &middot;
    <a href="#roadmap">Roadmap</a>
    &middot;
    <a href="https://github.com/sanketshinde3001/qwen-image-studio/issues">Report Bug</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#features">Features</a></li>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
        <li><a href="#troubleshooting">Troubleshooting</a></li>
      </ul>
    </li>
    <li>
      <a href="#usage">Usage</a>
      <ul>
        <li><a href="#command-line">Command line</a></li>
      </ul>
    </li>
    <li>
      <a href="#how-it-works">How It Works</a>
      <ul>
        <li><a href="#how-it-fits-in-16-gb">How it fits in 16 GB</a></li>
        <li><a href="#how-it-got-fast">How it got fast</a></li>
        <li><a href="#benchmarks">Benchmarks</a></li>
        <li><a href="#architecture">Architecture</a></li>
        <li><a href="#privacy">Privacy</a></li>
      </ul>
    </li>
    <li><a href="#limitations">Limitations</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
    <li><a href="#star-history">Star History</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

[![Qwen-Image Studio][product-screenshot]](#usage)

Most guides say Qwen-Image 2.1 needs 32 GB or more. The full bf16 checkpoint is 33 GB, and the text encoder alone is 17.5 GB. This project gets the whole pipeline under 12 GB of peak memory and brings an image edit down from about 25 minutes to under 3, with a local web studio on top.

| | |
|---|---|
| Edit (Turbo, 768 px) | 1 min 50 s to 3 min |
| Generate (Turbo, 1024 px) | about 4 min |
| Peak memory | 10 to 12 GB |
| Idle memory (engine warm) | about 1 GB |
| Disk | 11.6 GB |
| Tested on | MacBook with Apple M5, 16 GB unified memory, macOS 26.6 |

Why it exists:
* The model is excellent at instruction-based editing, and it should run on the laptops most people own.
* Iterating on an edit needs minutes, not half an hour.
* Your images and prompts should stay on your machine, with a mode that leaves no trace at all.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Features

**Editing**
* Instruction-based editing with up to 3 reference images
* Mask brush: paint the area to change and everything else stays pixel-identical
* Crop, rotate and flip an image before editing it
* ✨ Suggest edits and Describe, powered by the same Qwen3-VL model through llama.cpp
* Version history for every image: where an edit came from and every branch made from it
* Before and after slider, plus A/B compare for any two images
* Drop, paste or pick images (PNG, JPEG, WebP, HEIC from iPhone). Output can match your input's aspect ratio

**Generation and finishing**
* Text to image with style shortcuts, negative prompt, 7 aspect ratios and custom sizes up to 2048 px
* Up to 4 variations per run with consecutive seeds
* Upscale any result 2× or 4× with Real-ESRGAN

**Speed presets**

| Preset | Model | Size | Steps | Typical edit time |
|---|---|---|---|---|
| Turbo (default) | 4-step LoRA, warm engine | 768 | 4 | 1 min 50 s to 3 min |
| Draft | Full model + EasyCache, live preview | 512 | 10 | 2.5 to 3 min |
| Balanced | Full model + EasyCache | 768 | 16 | about 12 min (est.) |
| Quality | Full model | 1024 | 24 | 30+ min (est.) |

**Workflow**
* Queue with progress, speed and time left. Pause, reorder and cancel jobs
* Optional live preview after every step
* Time estimates that learn from real runs on your machine
* Gallery search, filters by type and date, and multi-select to download as a ZIP, compare or delete
* Prompt history, favorite prompts and your own saved presets
* Desktop notification when a job finishes in the background
* Complete delete and a Private mode (see [Privacy](#privacy))

![Viewer with history and before and after][viewer-screenshot]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![stable-diffusion.cpp][sdcpp-shield]][sdcpp-url]
* [![llama.cpp][llamacpp-shield]][llamacpp-url]
* [![Qwen-Image 2.1][qwen-shield]][model-url]
* [![Metal][metal-shield]][metal-url]
* [![Python][python-std-shield]][python-url]
* [![Real-ESRGAN][esrgan-shield]][esrgan-url]

No Homebrew, pip, conda or Hugging Face cache. The server uses only the Python that ships with macOS, the UI is one HTML file with no build step, and everything lives in this folder.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* Apple Silicon Mac (M1 or newer) with 16 GB of memory or more
* macOS 26. The prebuilt binaries target it. On older macOS, build stable-diffusion.cpp from source and put `sd-cli` and `sd-server` in `bin/`
* About 12 GB of free disk space
* Python 3, which macOS already includes
  ```sh
  /usr/bin/python3 --version
  ```

### Installation

1. Clone the repo
   ```sh
   git clone https://github.com/sanketshinde3001/qwen-image-studio.git
   cd qwen-image-studio
   ```
2. Download the binaries and models (about 11.6 GB). You can run it again at any time. It skips finished files, checks sizes and resumes partial downloads.
   ```sh
   ./download.sh
   ```
3. Start the studio. It opens http://127.0.0.1:7860 in your browser. Press Ctrl+C to stop it, or pass a port such as `./studio.sh 8080`.
   ```sh
   ./studio.sh
   ```

What `download.sh` fetches:

| File | Size | Source |
|---|---|---|
| `sd-cli`, `sd-server` (Metal build) | 35 MB | [leejet/stable-diffusion.cpp][sdcpp-url] |
| `llama-mtmd-cli` (for Suggest and Describe) | 30 MB | [ggml-org/llama.cpp][llamacpp-url] |
| Diffusion transformer, Q4_K_M | 4.2 GB | [unsloth/Qwen-Image-2.1-GGUF](https://huggingface.co/unsloth/Qwen-Image-2.1-GGUF) |
| Qwen3-VL-8B text encoder, UD-Q4_K_XL | 5.1 GB | [unsloth/Qwen3-VL-8B-Instruct-GGUF](https://huggingface.co/unsloth/Qwen3-VL-8B-Instruct-GGUF) |
| Qwen3-VL vision projector, F16 | 1.2 GB | same repo |
| VAE, bf16 | 0.7 GB | [unsloth/Qwen-Image-2.1-FP8](https://huggingface.co/unsloth/Qwen-Image-2.1-FP8) |
| Fun-Acc 4-step LoRA | 0.3 GB | [eastmoe/Qwen-Image-2.1-Fun-Acc-LoRAs-Comfy](https://huggingface.co/eastmoe/Qwen-Image-2.1-Fun-Acc-LoRAs-Comfy) |
| Real-ESRGAN x4plus | 64 MB | [xinntao/Real-ESRGAN][esrgan-url] |

The server only listens on 127.0.0.1, so other devices on your network can't reach it.

### Troubleshooting

**"sd-cli can't be opened because Apple cannot check it for malicious software."** The binaries came through a browser download, which marks them as quarantined. Clear the flag:
```sh
xattr -dr com.apple.quarantine bin
```

**Very slow runs or heavy swap.** Close memory-hungry apps such as browsers with many tabs. Sizes above about 1.3 megapixels (output plus reference images) can go past 16 GB, and the studio warns you before you start one.

**Runs get slower over a long session.** That's heat. On this MacBook, Turbo steps took about 16 s when cool and 28 to 30 s after back-to-back runs. Short breaks bring it back.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- USAGE EXAMPLES -->
## Usage

1. Drop an image into the Edit tab, or press Edit on a gallery image.
2. Optional: press **Mask** to paint just the area to change, **Crop** to reframe, or **✨ Suggest edits** for ideas.
3. Describe the change. Short, concrete instructions work best, and it helps to say what should stay the same: "Make his cap red. Keep his face and pose unchanged."
4. Press Edit or ⌘ Enter. Keep working while it runs, since jobs queue up.
5. When an instruction works, run it again with Quality or press **Upscale** for the final version.

Deep links are handy for scripting or bookmarking:

```
http://127.0.0.1:7860/#edit=<gallery file>&prompt=<text>   open with an image ready to edit
http://127.0.0.1:7860/#view=<gallery file>                  open an image in the viewer
```

### Command line

The studio is optional. The scripts call the same binary.

```sh
./generate.sh "a lighthouse at dawn, photorealistic" 1024 1024 20 42
TURBO=1 ./generate.sh "a lighthouse at dawn, photorealistic" 768 768

./edit.sh photo.jpg "make the sky stormy, keep everything else" 42
TURBO=1 ./edit.sh photo.jpg "make the sky stormy, keep everything else"
```

Arguments: `generate.sh prompt [width] [height] [steps] [seed]` and `edit.sh image instruction [seed] [reference px]`. Results go to `outputs/`. The scripts use the original Turbo grid and don't use the warm engine.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- HOW IT WORKS -->
## How It Works

### How it fits in 16 GB

Qwen-Image 2.1 has three parts: a 7B diffusion transformer (DiT), an 8B Qwen3-VL model used as the text and image encoder, and a VAE.

| Component | bf16 | This setup |
|---|---|---|
| Qwen3-VL-8B encoder | 17.5 GB | 5.1 GB (UD-Q4_K_XL) |
| Diffusion transformer | 14.2 GB | 4.2 GB (Q4_K_M) |
| VAE | 1.3 GB | 0.7 GB |
| Vision projector (editing only) | | 1.2 GB |
| **Total** | **33 GB** | **11.2 GB** |

Other Mac setups, such as mflux and Core ML, keep the text encoder in bf16 to protect prompt quality. That alone is bigger than 16 GB. Unsloth's dynamic 4-bit quant keeps the most sensitive layers at higher precision, and in practice prompt following held up well.

Memory is kept down in a few more ways:

* **Disk-backed weights.** The warm engine memory-maps its weights (`--mmap --params-backend disk`). macOS can drop those pages under pressure instead of swapping, so the idle engine holds about 1 GB instead of 10.
* **Quantized prefix cache.** The DiT caches the text prefix for every layer. With `qwen_image_2_1_prefix_cache_type=q8_0` that cache takes about 1 GB instead of 4 GB in f32.
* **Flash attention** in the DiT (`--diffusion-fa`) keeps attention memory linear in sequence length.
* **One heavy process at a time.** Jobs that need a separate process, such as live preview, unload the warm engine first, so two copies of the models never share 16 GB.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### How it got fast

Every step was measured on the same machine. Times are wall-clock and include model loading.

1. **Baseline: full model, 1024 px, 20 steps, CFG 6.** 27 minutes, about 75 s per step. It fits in memory, but it's too slow to iterate on.

2. **Reference resolution control.** In edit mode the reference image is tokenized and joined to the sequence the DiT attends over. A 1024 px reference nearly doubles the work compared to generation. The studio resizes references to 512, 768 or 1024 px before the run, and never enlarges small ones.

3. **EasyCache.** stable-diffusion.cpp can skip transformer passes when consecutive steps barely change the output (`--cache-mode easycache`). Combined with 512 px and 10 steps this gives the Draft preset.

4. **The 4-step distillation LoRA (the big one).** Alibaba PAI released [Qwen-Image-2.1-Fun-Acc](https://huggingface.co/alibaba-pai/Qwen-Image-2.1-Fun-Acc-LoRAs), trained with Parallel Decoding Distillation, covering both text to image and editing. Their sampler code showed two things that matter here: it runs at **CFG 1**, so each step needs one transformer pass instead of two, and it is distilled on a **fixed sigma grid**, which stable-diffusion.cpp accepts as custom sigmas. That's 4 transformer passes instead of 20 × 2 = 40. The original checkpoint switches between four output heads per step, which a standard LoRA can't express, so the ComfyUI conversion averages them into one `proj_out` diff (the converter reports about 0.5% error). stable-diffusion.cpp loads all 678 tensors and applies them at runtime on top of the Q4 weights. A 768 px edit went from about 100 s per step × 16 steps to about 2.5 minutes in total.

5. **A sigma grid matched to the output size.** Alibaba's grid (`1.0, 0.917, 0.786, 0.549, 0.0`) was made for 2048 px. Qwen's scheduler shifts its schedule by the image's token count, so the studio fits the shift value behind that grid and moves it the same way for your size. At 768 px it becomes `1.0, 0.859, 0.667, 0.389, 0.0`. Same speed, but in a side-by-side test with the same seed, the matched grid gave sharper texture and followed a secondary instruction ("gently snowing") that the original grid missed. The original grid is one click away in More settings.

6. **A warm engine.** Instead of starting `sd-cli` for every job, the studio keeps `sd-server` running with its weights memory-mapped from disk. It skips process start-up, model loading and graph building, and repeated prompts hit its conditioning cache, which saves the 15 to 18 s prompt encoding. Under the same conditions a Turbo edit took 184 to 200 s warm against 220 s cold. It unloads after 10 idle minutes (adjustable). Keeping the weights fully resident was tested first and was slower: it pushed the Mac to 4.3 GB of swap and every step slowed down.

7. **Untiled VAE.** Decoding the final image took 33 s tiled at 768 px and 16 s untiled, with no extra swap. At 1024 px untiled decoding took 31 s and still fit. The studio only tiles above 1.25 megapixels.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Benchmarks

Apple M5, 16 GB, macOS 26.6, stable-diffusion.cpp `master-929-3f8527a`, Metal backend.

| Task | Settings | Time | Per step | Peak memory |
|---|---|---|---|---|
| Generate | 1024 px, 20 steps, CFG 6 | 26 min 55 s | 76 s | 10.0 GB |
| Edit | 768 px + 768 ref, CFG 6 | ~27 min (projected) | ~100 s | |
| Edit, Draft | 512 px + 512 ref, 10 steps, EasyCache | 2 min 18 s | 18 s | |
| Generate, Turbo | 1024 px, 4 steps | 4 min 13 s | 44 s | 10.4 GB |
| Generate, Turbo | 512 px, 4 steps | 46 s | 6 s | |
| Edit, Turbo, cold | 768 px + 768 ref | 2 min 31 s | 16 s | 12.0 GB |
| Edit, Turbo, warm engine, masked | 768 px + 768 ref, includes engine start | 1 min 49 s | 16 s | |
| Upscale 2× | 768 → 1536 px, Real-ESRGAN | 2 min 55 s | | |
| Upscale 4× | 768 → 3072 px, Real-ESRGAN | 3 min 20 s | | |
| Suggest edits | Qwen3-VL-8B, one image | about 22 s | | about 6 GB |

Speeds vary by a few percent from run to run, and a lot with heat (see [Troubleshooting](#troubleshooting)).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Architecture

```
Browser (studio/index.html, one file, no build step)
   │  JSON over HTTP, polled every 1.5 s while busy
   ▼
studio/server.py   HTTP, job queue, storage, private mode      (Python standard library)
   ├─ one worker thread, so one job uses the GPU at a time
   ├─ resizes references with sips, converts HEIC and WebP, builds init + mask for masked edits
   ├─ writes results + JSON sidecars, or keeps them in memory in private mode
   └─ learns speed per mode from real runs (studio/calibration.json)
   ▼
studio/engine.py   everything that touches the GPU
   ├─ WarmEngine    bin/sd-server, kept running, weights memory-mapped, idle unload
   ├─ ColdRun       bin/sd-cli for live preview and upscaling, bin/llama for the assistant
   ├─ Progress      turns log lines into stage, step, speed and time left
   └─ turbo_sigmas  the size-matched sigma grid
```

Masked edits send the original as the init image plus a mask and the same image as a reference, at strength 1.0. The model follows the instruction inside the mask, and the latent outside it is kept from the original at every step.

sd-server can't stop a job mid-run, so cancelling a warm job restarts the engine. The next job pays the start-up again (about 20 s).

```
studio.sh          start the web UI
download.sh        fetch binaries and models
generate.sh        command-line generation
edit.sh            command-line editing
cleanup.sh         delete everything
studio/
  server.py        HTTP server, queue, storage
  engine.py        warm engine, cold runs, assistant, sigma grid
  index.html       the whole UI
docs/              logo and screenshots
bin/               sd-cli, sd-server, llama.cpp       (downloaded)
models/            weights, LoRA, upscaler            (downloaded)
inputs/            uploads and masks                  (created)
outputs/           results and .json settings         (created)
logs/              one log per job                    (created)
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Privacy

* The server listens on 127.0.0.1 only. Nothing is sent anywhere after `download.sh`.
* Generated images don't embed your prompt. stable-diffusion.cpp writes it into PNG metadata by default, and the studio turns that off.
* **Private mode** keeps results and uploads in `studio/tmp/private/` only. It writes no logs, settings files, gallery entries or speed data, and desktop notifications leave out the prompt. The mode is held by the server, so a page reload can't turn it off, and any edit made from a private image stays private. Everything is erased when you press Discard, when the studio stops, and on the next start in case it crashed. Download or Keep what you want first.
* **Delete** removes the image, its settings, every log that mentions it, and uploads or masks nothing else uses.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LIMITATIONS -->
## Limitations

* **Turbo trades some quality for speed.** It renders English text inside images less reliably than the full model, and generations can look a little darker. Use Quality for text-heavy or detailed finals.
* **The matched sigma grid is fitted, not official.** It reproduces the shape of Alibaba's grid and moves it with Qwen's own shift rule. It tested better at 768 px, but Alibaba hasn't published grids for other sizes.
* **The averaged output head** in the ComfyUI conversion is a close approximation of the original four-head model, not an exact match.
* **Upscaling looks slightly smoothed.** Real-ESRGAN sharpens edges well but can flatten fine skin and fabric texture.
* **One job at a time.** 16 GB has room for one run, so jobs queue. The assistant needs about 6 GB while it runs.
* **Speeds are for a base M5 in a fanless body.** Pro and Max chips have more GPU cores and cooling and should be several times faster.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ROADMAP -->
## Roadmap

- [x] Run Qwen-Image 2.1 in 16 GB with 4-bit GGUF weights
- [x] Web studio with queue, gallery and before and after
- [x] Private mode and complete delete
- [x] 4-step Turbo LoRA with a size-matched sigma grid
- [x] Warm engine with disk-backed weights
- [x] Mask brush, crop and rotate
- [x] Qwen3-VL Suggest edits and Describe
- [x] Version history and A/B compare
- [x] Real-ESRGAN upscaling
- [ ] Keyboard shortcuts in the gallery and viewer
- [ ] Phone-friendly layout, with opt-in access from your home network
- [ ] Batch the same instruction over a folder of images
- [ ] Live preview on the warm engine
- [ ] Inpainting-aware Turbo grid tuned for masked edits

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTRIBUTING -->
## Contributing

Contributions are welcome, especially benchmarks from other Macs (M1 to M5, Pro and Max) and quality comparisons between presets.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/your-change`)
3. Commit your changes (`git commit -m 'Add your change'`)
4. Push to the branch (`git push origin feature/your-change`)
5. Open a pull request

Please keep the studio free of third-party Python packages and the UI in one file, so it keeps working with the Python that ships with macOS.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

The studio code and scripts are distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.

Model weights and binaries keep their own licenses. Check each source in [Installation](#installation) before commercial use.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

Sanket Rajendra Shinde - [@sanketshinde3001](https://github.com/sanketshinde3001)

Project link: [https://github.com/sanketshinde3001/qwen-image-studio](https://github.com/sanketshinde3001/qwen-image-studio)

Questions, bugs and benchmark results: [open an issue](https://github.com/sanketshinde3001/qwen-image-studio/issues).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* [Qwen-Image 2.1](https://github.com/QwenLM/Qwen-Image-2.1) by the Qwen team, Alibaba
* [stable-diffusion.cpp][sdcpp-url] by leejet and contributors, MIT license
* [llama.cpp][llamacpp-url] by ggml-org and contributors, MIT license
* GGUF quantizations by [Unsloth](https://huggingface.co/unsloth)
* [Qwen-Image-2.1-Fun-Acc](https://huggingface.co/alibaba-pai/Qwen-Image-2.1-Fun-Acc-LoRAs) by Alibaba PAI, with the ComfyUI conversion by [eastmoe](https://huggingface.co/eastmoe/Qwen-Image-2.1-Fun-Acc-LoRAs-Comfy)
* [Real-ESRGAN][esrgan-url] by Xintao Wang et al., BSD 3-Clause license
* README layout based on [Best-README-Template](https://github.com/othneildrew/Best-README-Template)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- STAR HISTORY -->
## Star History

<a href="https://star-history.com/#sanketshinde3001/qwen-image-studio&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=sanketshinde3001/qwen-image-studio&type=Date&theme=dark" />
    <img alt="Star history chart" src="https://api.star-history.com/svg?repos=sanketshinde3001/qwen-image-studio&type=Date" />
  </picture>
</a>

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- MARKDOWN LINKS & IMAGES -->
[macos-shield]: https://img.shields.io/badge/macOS-Apple%20Silicon-000000?style=for-the-badge&logo=apple&logoColor=white
[macos-url]: https://support.apple.com/en-us/116943
[memory-shield]: https://img.shields.io/badge/Runs%20in-16%20GB-f0a14a?style=for-the-badge
[python-shield]: https://img.shields.io/badge/Python-3%20stdlib-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://docs.python.org/3/library/
[deps-shield]: https://img.shields.io/badge/pip%20installs-none-2ea44f?style=for-the-badge
[model-shield]: https://img.shields.io/badge/Qwen--Image-2.1-6f42c1?style=for-the-badge
[model-url]: https://github.com/QwenLM/Qwen-Image-2.1
[product-screenshot]: docs/studio.jpg
[viewer-screenshot]: docs/compare.jpg
[sdcpp-shield]: https://img.shields.io/badge/stable--diffusion.cpp-Metal-333333?style=for-the-badge
[sdcpp-url]: https://github.com/leejet/stable-diffusion.cpp
[llamacpp-shield]: https://img.shields.io/badge/llama.cpp-Qwen3--VL-333333?style=for-the-badge
[llamacpp-url]: https://github.com/ggml-org/llama.cpp
[qwen-shield]: https://img.shields.io/badge/Qwen--Image-2.1%20Q4__K__M-6f42c1?style=for-the-badge
[metal-shield]: https://img.shields.io/badge/Apple-Metal-000000?style=for-the-badge&logo=apple&logoColor=white
[metal-url]: https://developer.apple.com/metal/
[python-std-shield]: https://img.shields.io/badge/Python-standard%20library-3776AB?style=for-the-badge&logo=python&logoColor=white
[esrgan-shield]: https://img.shields.io/badge/Real--ESRGAN-x4plus-333333?style=for-the-badge
[esrgan-url]: https://github.com/xinntao/Real-ESRGAN
[license-shield]: https://img.shields.io/badge/License-MIT-2ea44f?style=for-the-badge
[license-url]: LICENSE
[stars-shield]: https://img.shields.io/github/stars/sanketshinde3001/qwen-image-studio?style=for-the-badge
[stars-url]: https://github.com/sanketshinde3001/qwen-image-studio/stargazers
[views-shield]: https://hits.sh/github.com/sanketshinde3001/qwen-image-studio.svg?style=for-the-badge&label=views&color=f0a14a
[views-url]: https://hits.sh/github.com/sanketshinde3001/qwen-image-studio/
