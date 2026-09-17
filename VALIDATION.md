# Validation report — 2026-09-17

**Result: native pack discovery, parsing, shader compilation, reflection, binding,
SPIR-V validity, static interfaces and synthetic software Vulkan post-processing
and shadow-receiver pixel checks PASS. In-game rendering is NOT tested.**

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

## 0.1.4 gameplay and visual changes

The terrain shader adds native/balanced/smooth shadow filtering, adjustable softness
and cast-shadow strength. Defaults are balanced (4 bilinear comparison gathers per
sampled map), softness 1 and strength 0.85. Smooth uses 9 weighted gathers; softness
0 uses one bilinear comparison. Native mode calls the release's original sampler
and ignores the softness option. It still uses this pack's strength/lighting model.
Sampling is deterministic, without temporal noise or history. The existing loader
coordinate, slope-gradient and normal-offset helpers and precision bias are retained.

Terrain and entity visibility combine with `min`, avoiding double attenuation when
their shadows overlap. Cast visibility attenuates direct illumination and leaf
transmission/specular, while ambient fill and block light remain visible. Strength
0 bypasses receiver attenuation but does not stop shadow-map rendering; quality 0
is required to disable the loader's shadow producer and its allocation.

Cascade blending begins within the release renderer's fitted overlap (the next
cascade starts at 0.82 times the previous split; blending starts no earlier than
0.84 times it). The final cascade fades over its last 18 percent. PCF footprint
bounds are checked before texture gathering. Analytic water/wet-surface sky
reflections also include the existing directional sunrise/sunset glow.

There are no new graph passes, targets or shadow-map allocations. Extra filtering
increases sampling work, including entity maps and a second cascade at transitions.
Hardware frame times and real scene quality are unmeasured.

## Checks

| Check | Result |
| --- | --- |
| ZIP integrity and one root `sulkan.json` | PASS |
| Actual `ShaderPackScanner.scanDirectory` | PASS; archive is supported |
| Actual `PackFiles.read` and `PackGraph.parse` | PASS |
| Native options | 28 definitions, 107 permitted values accepted |
| Test scenarios | 33 |
| Expanded shader entrypoints | 249 production + 15 diagnostic |
| Native compiler + Minecraft reflection | 316 production + 15 diagnostic modules PASS |
| Minecraft `IntermediaryShaderModule.rebind` | 331 modules PASS |
| `spirv-val --target-env vulkan1.2` after rebinding | 331 modules PASS |
| Vertex-to-fragment name/type/location/flat linkage | 297 pairs PASS |
| Sodium five-attribute vertex ABI | PASS |
| Shared UBO member offsets, including SulkanShadowData | PASS |
| Sodium push constants | PASS: offsets 0, 12, 16 |
| Graph schedules with bloom and AO disabled | PASS: 2 post passes remain |
| Allocation accounting at 720p/1080p/1440p/4K | PASS within 448 MiB manifest limit |
| Synthetic Vulkan draws with release-compiled post shaders | 50 draws PASS |
| Pixel assertions: bloom/dither/AO plus atmosphere behavior and exclusions | 18 checks PASS |
| Synthetic Vulkan draws using production shadow helper | 24 draws PASS |
| Shadow assertions: filtering, occlusion, bias, bounds and transitions | 13 checks PASS |

Scenarios cover defaults, minimal effects, enhanced settings, all numerical maxima,
each shadow tier 0–3 with water both on and off, AO disabled, zero AO strength,
eight-sample AO, bloom disabled, edge smoothing enabled, bloom disabled with edge smoothing enabled,
cave visibility disabled, wet surfaces disabled, dithering disabled, each atmosphere effect disabled,
both disabled, isolated atmosphere on/off, an elevated fog reference, and six explicit
shadow-filter/softness/strength cases. Geometry fragments
are compiled as opaque and with both `ALPHA_CUTOUT=0.1` and `ALPHA_CUTOUT=0.5`.
The fullscreen vertex shader is the loader's actual embedded source.

Binding tests construct descriptors from the known native contract and exercise
Minecraft's real `rebind` routine. The SPIR-V checks validate the remapped modules.
The separate `NativeRenderProbe` then creates a Vulkan device, descriptor pools,
graphics pipelines and offscreen targets for post-process and shadow diagnostic variants.
It executes 50 draws using 128x128 synthetic source/depth fixtures, and reads pixels
back for assertions. Final color uses the pack's `RGBA8_UNORM` format. Diagnostic
AO/bloom/compose targets use `RGBA32_FLOAT` to inspect values; they do not replicate the
pack's half-float allocation. No swapchain or Minecraft runtime is created.

Atmosphere assertions compare the actual on/off compose modules using independently
constructed frames and textures: warm forward-facing twilight, no glow at noon/night
or behind the sun, rain attenuation of glow, rain strengthening of unsaturated mist,
reference-altitude response, bounded opacity, and the balanced defaults. Sky and
geometry are both exercised for Nether/End/custom dimensions and water/lava/powder
snow. Near objects, dark interiors, high altitude, deep underground, and held items
are checked against the disabled variant. These are synthetic correctness checks,
not screenshots or measurements of real Minecraft environments.

The shadow suite adds 24 draws with independently constructed 64x64 terrain/entity
depth maps and 128x128 receiver positions/normals. `tools/shadow-probe.fsh` is a
diagnostic entrypoint that calls the production `auroraShadowVisibility` helper;
the graph never schedules it. It uses the release include expander/compiler and
the actual `SulkanShadowData` member layout (offsets 0/256/320/336, with a 416-byte
buffer matching the release upload). Two UBOs and eight samplers are rebound and
rendered by the Vulkan probe. The suite checks both map types, overlapping maps,
time-stable output, softer edges, strength changes, quality/strength/dimension
bypasses, out-of-map/depth receivers, a coplanar sloped receiver, distance fade,
cascade handoff, and skipped inactive cascades. Terrain production shaders are
compiled and linked, but their Sodium draw path and game-generated occluder maps
are not exercised by these fixtures. Passing the synthetic slope check does not
establish that all real-world shadow acne or light leakage is eliminated.

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
python3 tools/shadow_checks.py build/validation --java java --classpath "build/probe:$AURORA_TEST_CP"
```

The test fails if there is no Vulkan device. For a locally extracted lavapipe,
set `VK_DRIVER_FILES` to its ICD JSON and make its library directory discoverable
by the dynamic loader. `render-checks.json` and `shadow-checks.json` record the selected
device, assertions and pixel/SPIR-V hashes. Synthetic fixtures stay under `build/validation`.

After successful checks, collect the distributable report and rebuild the ZIP:

```bash
python3 tools/collect_validation.py build/validation --archive build/aurora.zip --loader /path/to/sulkan-0.4.2-26.2.jar --client /path/to/minecraft-26.2-client.jar
python3 tools/build.py --output UN_Aurora_Lite-0.1.4-Sulkan-0.4.2.zip
```

The collector rejects manifest/shader/diagnostic-entrypoint changes made after the
tested ZIP was built, and verifies pixel reports against the compiled module hashes.

## Remaining runtime checks

A software Vulkan device was used for isolated post-process and shadow-receiver draws. Fabric/Sodium
mixin installation, Minecraft terrain pipeline creation, world rendering, reload
stability, physical AMD/Intel/NVIDIA drivers, frame times and game screenshots
remain unverified. Software pixel checks are not hardware performance evidence.

The pack should now meet the checked Sulkan 0.4.2 loading contracts, but full success
still requires loading a world on the target installation. Use the five-minute
checklist in `README.md`; retain the instance's `logs/latest.log` if it fails.

Machine-readable results and manifest/shader hashes are in `validation/summary.json`,
`validation/scenarios.json`, `validation/modules.json`, `validation/memory-budget.json`,
`validation/render-checks.json` and `validation/shadow-checks.json`.
