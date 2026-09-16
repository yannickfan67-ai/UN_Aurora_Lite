# Provenance and license

UN Aurora Lite 0.1.2 is licensed under **GPL-3.0-only**. See `LICENSE`.

## New work

`sulkan.json`, all visual shading files other than `shaders/vegetation-wind.glsl`,
the tools, and the documentation were authored for this pack.
The native graph manifest, material IDs, Sodium interface, and loader-provided includes
were studied from the Sulkan release to preserve its functional contracts.
The visual shader implementation in Sulkan Realistic is not redistributed here.

## Sulkan helper

`shaders/vegetation-wind.glsl` is a byte-identical copy of
`assets/sulkan/shaders/include/vegetation_wind.glsl` from Sulkan 0.4.2,
by mravatin / the Sulkan contributors, under GPL-3.0-only.
It is shared with the loader's shadow caster so wind deformation is consistent.

`sulkan/frame.glsl`, `sulkan/shadows.glsl` and `sulkan/shadow-filter.glsl`
are includes supplied at runtime by Sulkan. Their UBO declarations and shadow
implementations are not replaced by this pack.

References:

- [Sulkan release versions](https://modrinth.com/project/jqg5mkGh/versions)
- [Sulkan source and GPL license](https://github.com/mravatins/sulkanShaders)
- [Sulkan shader reference](https://sulkan.org/api/), consulted with the caveat that its old entrypoint template does not describe the complete 0.4.2 graph format.

Sulkan, Minecraft, Sodium, Gson, LWJGL, Java, Mesa, NumPy and SPIR-V Tools binaries are **not**
included. Test tools use the original installed release classes and require those
dependencies separately. Upstream game tests mentioned in Sulkan Realistic's
documentation are not tests of UN Aurora Lite and are not claimed here.
