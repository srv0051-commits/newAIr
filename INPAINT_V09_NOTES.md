# newAIr Inpainting Precision Upgrade

This build keeps the existing Face -> Full Scene / model switching code and upgrades the dedicated SD 1.5 inpainting path.

## What changed
- Fixed the crop-resize compositing bug that could create hard rectangular seams.
- Generated crops are always resized back to the exact original crop dimensions before compositing.
- Unmasked pixels are restored from the original source image.
- Separate inference and final-composite masks.
- Context padding and mask expansion give the diffusion model room to rebuild boundaries.
- Final feather is applied only during compositing.
- Aspect ratio is preserved while preparing the diffusion working crop.
- Working size is constrained for RTX 3050 6 GB friendly inference.
- Added Precise / Balanced / Creative inpainting presets.
- Added stronger seam, halo, collage, perspective and texture-continuity negatives.

## Important
No diffusion system can guarantee a perfect semantic edit every time. The upgrade is designed to make the editor geometrically correct, seam-resistant, and predictable while preserving everything outside the selected region.

The existing database is not modified by this patch.
