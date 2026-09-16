# Validation report — 2026-09-16

**Result: native pack discovery, parsing, shader compilation, reflection, binding,
SPIR-V validity, static interfaces and synthetic software Vulkan post-processing
pixel checks PASS. In-game rendering is NOT tested.**

## Reference inputs

- Sulkan `0.4.2`, released 2026-09-08, primary JAR obtained from Modrinth.
- Loader SHA-256: `16706186ca430b55f8636d8ff57545ed782202f7a6814eef933f61a821b3b8ca`.
- Minecraft Java `26.2` client JAR and its LWJGL `3.4.1` libraries.
- Java `25` runtime for the release classes; Java `17` compiler for the reflection probes.
- SPIR-V Tools `2023.6`, target environment `vulkan1.2`.
- Mesa `25.2.8` lavapipe, device `llvmpipe (LLVM 20.1.2, 256 bits)`, for synthetic offscreen draws.
- The old public main source and website starter were consulted but not used as the current manifest contract.

The scanner, graph parser, include expander, generated `SulkanFrame` declaration,
native shader compiler, SPIRV-Cross reflection and descriptor rebind implementation
were executed directly from the unmodified release JARs. They were not replaced by
Python approximations, patched class versions or mock frame/format definitions.

## 0.1.2 gameplay and visual changes

The balanced defaults retain modest bloom, AO and water reflections, with readable
nights/interiors. Sun and moon diffuse lobes now fade individually at the horizon.
Rain adds an optional restrained sheen on exposed upward faces. Water waves use
derivative filtering for distant pixels and periodic phases across camera wraps.
Bloom extraction rejects the hand's complete bilinear footprint before blur.
Static, sub-code-value dithering improves 8-bit gradients while preserving black.
AO skips its neighborhood samples beyond the existing 96-block fade range.
No render targets or post passes were added. The extra math and hand-depth gathers
have not been benchmarked on hardware.

## Checks

| Check | Result |
| --- | --- |
| ZIP integrity and one root `sulkan.json` | PASS |
| Actual `ShaderPackScanner.scanDirectory` | PASS; archive is supported |
| Actual `PackFiles.read` and `PackGraph.parse` | PASS |
| Native options | 22 definitions, 83 permitted values accepted |
| Test scenarios | 21 |
| Expanded active shader entrypoints | 156 |
| Native compiler + Minecraft reflection | 199 modules PASS |
| Minecraft `IntermediaryShaderModule.rebind` | 199 modules PASS |
| `spirv-val --target-env vulkan1.2` after rebinding | 199 modules PASS |
| Vertex-to-fragment name/type/location/flat linkage | 177 pairs PASS |
| Sodium five-attribute vertex ABI | PASS |
| Shared UBO member offsets | PASS |
| Sodium push constants | PASS: offsets 0, 12, 16 |
| Graph schedules with bloom and AO disabled | PASS: 2 post passes remain |
| Allocation accounting at 720p/1080p/1440p/4K | PASS within 448 MiB manifest limit |
| Synthetic Vulkan draws with release-compiled post shaders | 9 draws PASS |
| Pixel assertions: hand bloom, static dither, black level, flat/far/sky AO | 8 checks PASS |

Scenarios cover defaults, minimal effects, enhanced settings, all numerical maxima,
each shadow tier 0–3 with water both on and off, AO disabled, zero AO strength,
eight-sample AO, bloom disabled, edge smoothing enabled, bloom disabled with edge smoothing enabled,
cave visibility disabled, wet surfaces disabled and dithering disabled. Geometry fragments
are compiled as opaque and with both `ALPHA_CUTOUT=0.1` and `ALPHA_CUTOUT=0.5`.
The fullscreen vertex shader is the loader's actual embedded source.

Binding tests construct descriptors from the known native contract and exercise
Minecraft's real `rebind` routine. The SPIR-V checks validate the remapped modules.
The separate `NativeRenderProbe` then creates a Vulkan device, descriptor pools,
graphics pipelines and offscreen targets for five post-process module variants.
It executes 9 draws using 128x128 synthetic source/depth fixtures, and reads pixels
back for assertions. Final color uses the pack's `RGBA8_UNORM` format. Diagnostic
AO/bloom targets use `RGBA32_FLOAT` to inspect values; they do not replicate the
pack's half-float allocation. No swapchain or Minecraft runtime is created.

## Allocation scope

`PackGraph.allocationBytes` is executed from the release. Additional budget estimates
follow `ShadowService.memoryBytes`' published class formula and use conservative
scene capture formats: one `RGBA8_UNORM` (4 bytes per pixel) plus two
`D32_FLOAT_S8_UINT` captures (8 bytes each, verified from Minecraft's `GpuFormat`).
The loader's shadow budget formula uses 5 bytes per shadow-map texel; this is its
budget accounting, not a claim about physical device allocation granularity.

| Resolution | Default graph targets | Conservative default budget | All-maximum budget |
| --- | ---: | ---: | ---: |
| 1280 × 720 | 12.30 MiB | 43.95 MiB | 161.13 MiB |
| 1920 × 1080 | 27.69 MiB | 81.30 MiB | 198.49 MiB |
| 2560 × 1440 | 49.22 MiB | 133.59 MiB | 250.78 MiB |
| 3840 × 2160 | 110.74 MiB | 283.01 MiB | 400.20 MiB |

The manifest limit is an upper guard, not an allocation request. These numbers
exclude base game targets, chunk meshes, atlases, driver overhead, and resource
generations that may temporarily coexist during reload. They are not measured VRAM.

## Reproduce

The release binaries are not distributed in this ZIP. Supply Java 25 and a Java
compiler, the exact Sulkan JAR, the Minecraft 26.2 client, Gson, and the corresponding
Minecraft libraries, including Linux LWJGL core, shaderc and SPIRV-Cross natives.
Set `AURORA_TEST_CP` to a Java classpath containing those installed JARs.

From the unpacked source folder:

```bash
python3 tools/build.py --output build/aurora.zip
javac -cp "$AURORA_TEST_CP" -d build/probe tools/LoaderProbe.java tools/NativeCompileProbe.java
java --enable-native-access=ALL-UNNAMED -cp "build/probe:$AURORA_TEST_CP" LoaderProbe build/aurora.zip build/validation
java --enable-native-access=ALL-UNNAMED -cp "build/probe:$AURORA_TEST_CP" NativeCompileProbe build/validation
python3 tools/validate_spirv.py build/validation
```

`spirv-val` must be on PATH or passed through `--spirv-val /absolute/path/to/spirv-val`.
Probe outputs are written to `build/validation`; that build directory is excluded
from distributable ZIPs. Optional settings are edited in-game, not through these tools.

For the optional pixel checks, install NumPy and a working Vulkan driver (hardware
or lavapipe). Add LWJGL Vulkan to the classpath, then run:

```bash
javac -cp "$AURORA_TEST_CP" -d build/probe tools/NativeRenderProbe.java
python3 tools/render_checks.py build/validation --java java --classpath "build/probe:$AURORA_TEST_CP"
```

The test fails if there is no Vulkan device. For a locally extracted lavapipe,
set `VK_DRIVER_FILES` to its ICD JSON and make its library directory discoverable
by the dynamic loader. `render-checks.json` records the selected device, assertions
and pixel/SPIR-V hashes. Synthetic fixture files stay under `build/validation`.

After successful checks, collect the distributable report and rebuild the ZIP:

```bash
python3 tools/collect_validation.py build/validation --archive build/aurora.zip --loader /path/to/sulkan-0.4.2-26.2.jar --client /path/to/minecraft-26.2-client.jar
python3 tools/build.py --output UN_Aurora_Lite-0.1.2-Sulkan-0.4.2.zip
```

The collector rejects manifest/shader changes made after the tested ZIP was built.

## Remaining runtime checks

A software Vulkan device was used for isolated post-process draws. Fabric/Sodium
mixin installation, Minecraft terrain pipeline creation, world rendering, reload
stability, physical AMD/Intel/NVIDIA drivers, frame times and game screenshots
remain unverified. Software pixel checks are not hardware performance evidence.

The pack should now meet the checked Sulkan 0.4.2 loading contracts, but full success
still requires loading a world on the target installation. Use the five-minute
checklist in `README.md`; retain the instance's `logs/latest.log` if it fails.

Machine-readable results and manifest/shader hashes are in `validation/summary.json`,
`validation/scenarios.json`, `validation/modules.json` and `validation/memory-budget.json`.
