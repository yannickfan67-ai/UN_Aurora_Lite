#version 450
// SPDX-License-Identifier: GPL-3.0-only
#include "shaders/common.glsl"
#include "shaders/sodium-abi.glsl"
#include "sulkan/shadows.glsl"
uniform sampler2D u_BlockTex;
uniform sampler2D u_LightTex;
uniform sampler2D Opaque;
uniform sampler2D OpaqueDepth;
layout(location = 0) in vec4 auroraTint;
layout(location = 1) in vec2 auroraUv;
layout(location = 2) in vec3 auroraPosition;
layout(location = 3) in vec2 auroraLight;
layout(location = 4) in float auroraFade;
layout(location = 5) flat in uint auroraMaterial;
layout(location = 0) out vec4 color;

vec3 auroraWaterSky(vec3 direction) {
    // Analytic sky reflection, without a second world render or ray tracing.
    vec3 horizon = max(auroraLinear(SkyColorAndStarBrightness.rgb), vec3(0.012, 0.02, 0.035));
    vec3 zenith = mix(vec3(0.006, 0.012, 0.035), vec3(0.10, 0.24, 0.46), auroraDay());
    vec3 skyColor = mix(horizon, zenith, smoothstep(0.0, 0.85, direction.y));
    vec3 overcast = max(auroraLinear(FogColorAndStart.rgb), vec3(0.005));
    return mix(skyColor, overcast, clamp(WorldTimeWeatherDimension.y, 0.0, 1.0) * 0.65);
}

void main() {
    vec4 texel = texture(u_BlockTex, auroraUv) * auroraTint;
    vec3 toEye = auroraNormalize(InverseView[3].xyz - auroraPosition);
    // Derivatives must execute before alpha discard or per-material branching.
    vec3 normal = auroraNormalize(cross(dFdx(auroraPosition), dFdy(auroraPosition)));
    normal *= dot(normal, toEye) < 0.0 ? -1.0 : 1.0;
#if WATER_ENABLED == 1
    // Integer cycles over 4096 blocks keep phase continuous as the camera wraps.
    vec2 waveWorld = auroraPosition.xz + mod(CameraPositionHighAndFogType.xz, vec2(4096.0))
                   + CameraPositionLowAndFarPlane.xz;
    vec2 wavePhase = vec2(dot(waveWorld, vec2(1108.0, 522.0)),
                         dot(waveWorld, vec2(-391.0, 913.0))) * (6.28318530718 / 4096.0);
    // Derivatives are evaluated before discard and divergent material branches.
    vec2 waveFilter = vec2(1.0) - smoothstep(vec2(0.4), vec2(2.8), fwidth(wavePhase));
#endif
#ifdef ALPHA_CUTOUT
    if (texel.a < float(ALPHA_CUTOUT)) discard;
#endif
    float distanceToEye = length(auroraPosition);
    float day = auroraDay();
    float rain = clamp(WorldTimeWeatherDimension.y, 0.0, 1.0);
    vec3 sunDirection = auroraNormalize(SunDirectionAndRainBrightness.xyz);
    vec3 moonDirection = auroraNormalize(MoonDirectionAndPhase.xyz);
    // Both celestial lobes fade to zero at the horizon. Do not rotate a mixed
    // sun/moon vector through zero or switch a half-strength diffuse lobe.
    float sunWeight = day * smoothstep(0.0, 0.12, sunDirection.y);
    float moonWeight = (1.0 - day) * smoothstep(0.0, 0.12, moonDirection.y);
    vec3 lightDirection = sunDirection.y >= moonDirection.y ? sunDirection : moonDirection;
    float visibility = sulkanTerrainShadow(auroraPosition, normal);
    float sky = auroraLight.y * auroraLight.y;
    float block = pow(auroraLight.x, 2.2);
    float sunset = (1.0 - smoothstep(0.05, 0.55, SunDirectionAndRainBrightness.y)) * day;
    vec3 sunlight = mix(vec3(1.02, 0.98, 0.90), vec3(1.35, 0.78, 0.40), sunset * float(LIGHT_WARMTH));
    vec3 moonlight = vec3(0.085, 0.12, 0.21) * float(NIGHT_BRIGHTNESS);
    vec3 directColor = sunlight * sunWeight + moonlight * moonWeight;
    vec3 diffuseLight = sunlight * sunWeight * max(dot(normal, sunDirection), 0.0)
                      + moonlight * moonWeight * max(dot(normal, moonDirection), 0.0);
    vec3 ambientColor = mix(vec3(0.05, 0.075, 0.13) * float(NIGHT_BRIGHTNESS),
        vec3(0.31, 0.40, 0.52), day);
    ambientColor = mix(ambientColor, vec3(dot(ambientColor, AURORA_LUMA)), rain * 0.5);
    vec3 lampColor = mix(vec3(1.0), vec3(1.28, 0.80, 0.46), float(LIGHT_WARMTH));
    vec3 illumination = vec3(0.025) + sky * ambientColor * (0.72 + 0.28 * max(normal.y, 0.0));
    illumination += sky * (0.15 * directColor + 0.85 * diffuseLight) * visibility * (1.0 - rain * 0.7);
    illumination += lampColor * block * 1.1;
    // Lift only unlit interiors, before multiplying by the block texture. Black
    // texels stay black; daylight and nearby torch light retain their contrast.
    float interior = (1.0 - smoothstep(0.10, 0.70, sky)) * (1.0 - smoothstep(0.02, 0.40, block));
    illumination += vec3(0.025 * float(CAVE_VISIBILITY) * interior);
    vec3 vanillaLight = auroraLinear(texture(u_LightTex, auroraLight * (15.0 / 16.0)).rgb);
    illumination = max(illumination, vanillaLight * (0.32 * float(CAVE_VISIBILITY) * interior));
    if (auroraMaterial == 5u) {
        // Restrained transmission on backlit leaves, gated by actual shadow visibility.
        float throughLeaf = pow(max(dot(-toEye, lightDirection), 0.0), 4.0);
        illumination += directColor * sky * visibility * throughLeaf * 0.12 * (1.0 - rain * 0.7);
    }
    // Dimension-specific lightmaps remain authoritative in the Nether and End.
    if (abs(WorldTimeWeatherDimension.w) > 0.5) {
        illumination = vanillaLight;
    }
    vec3 result = auroraLinear(texel.rgb) * max(illumination, vec3(0.0));
#if _SULKAN_ENABLED_WET_SURFACES
    if (rain > 0.001 && auroraMaterial != 1u && auroraMaterial != 9u && auroraOverworldAir()) {
        // A cheap analytic sheen on exposed upward faces; no extra scene capture.
        float wet = float(WET_SURFACES) * rain * smoothstep(0.88, 1.0, auroraLight.y)
                  * smoothstep(0.25, 0.9, normal.y);
        float grazing = pow(1.0 - max(dot(normal, toEye), 0.0), 5.0);
        result *= 1.0 - wet * 0.08;
        result += auroraWaterSky(reflect(-toEye, normal)) * wet * (0.015 + 0.12 * grazing);
    }
#endif
    if (auroraMaterial == 9u) {
        float emitter = smoothstep(0.3, 0.85, max(texel.r, max(texel.g, texel.b)));
        result = mix(result, auroraLinear(texel.rgb), emitter * float(EMISSIVE_STRENGTH));
    }

#if WATER_ENABLED == 1
    if (auroraMaterial == 1u && auroraOverworldAir()) {
        vec2 screen = gl_FragCoord.xy * ViewSizeAndInverse.zw;
        float time = TimeDeltaFrame.x;
        vec2 ripple = vec2(sin(wavePhase.x + time * 0.7),
                           cos(wavePhase.y - time * 0.5)) * waveFilter;
        vec3 waterNormal = auroraNormalize(normal + vec3(ripple.x, 0.0, ripple.y) * (0.025 * float(WATER_WAVES)));
        // Pixel-sized distortion keeps the riverbed readable at 720p through 4K.
        vec2 bend = ripple * float(WATER_WAVES) * 1.2 * ViewSizeAndInverse.zw / (1.0 + distanceToEye * 0.015);
        vec2 refracted = auroraSafeUv(screen + bend);
        float surfaceDepth = length(auroraViewPosition(screen, gl_FragCoord.z));
        float sampledDepth = texture(OpaqueDepth, refracted).r;
        float behindDepth = sampledDepth <= 1e-7 ? surfaceDepth + 48.0 : length(auroraViewPosition(refracted, sampledDepth));
        // Reject distortion across a nearer shoreline or foreground silhouette.
        if (behindDepth < surfaceDepth + 0.01) {
            refracted = auroraSafeUv(screen);
            sampledDepth = texture(OpaqueDepth, refracted).r;
            behindDepth = sampledDepth <= 1e-7 ? surfaceDepth + 48.0 : length(auroraViewPosition(refracted, sampledDepth));
        }
        vec4 background = texture(Opaque, refracted);
        if (background.a > 0.0) {
            float thickness = clamp(behindDepth - surfaceDepth, 0.0, 48.0);
            vec3 attenuation = exp(-thickness * float(WATER_DENSITY) * vec3(0.18, 0.065, 0.032));
            vec3 biomeWater = auroraLinear(clamp(auroraTint.rgb, 0.0, 1.0)) * 0.2;
            vec3 deepWater = mix(vec3(0.018, 0.09, 0.13), biomeWater, 0.28) * (0.15 + 0.60 * day + 0.25 * block);
            result = auroraLinear(background.rgb) * attenuation + deepWater * (1.0 - attenuation);
            float fresnel = 0.02 + 0.78 * pow(1.0 - max(dot(waterNormal, toEye), 0.0), 5.0);
            result = mix(result, auroraWaterSky(reflect(-toEye, waterNormal)),
                fresnel * sky * float(WATER_REFLECTION));
            vec3 halfVector = auroraNormalize(toEye + lightDirection);
            float sparkle = pow(max(dot(waterNormal, halfVector), 0.0), 96.0);
            result += directColor * sparkle * visibility * sky * (1.0 - rain) * 0.30;
            // Opaque snapshot already contains the background: do not blend it twice.
            texel.a = 1.0;
        }
    }
#endif
    float environmentFog = clamp((distanceToEye - u_EnvironmentFog.x) /
        max(u_EnvironmentFog.y - u_EnvironmentFog.x, 0.001), 0.0, 1.0);
    float cylinder = max(length(auroraPosition.xz), abs(auroraPosition.y));
    float renderFog = clamp((cylinder - u_RenderFog.x) / max(u_RenderFog.y - u_RenderFog.x, 0.001), 0.0, 1.0);
    float fog = max(1.0 - auroraFade, max(environmentFog, renderFog)) * u_FogColor.a;
    // Compress bright terrain before Minecraft's LDR target can clip it.
    result = auroraHighlightShoulder(result, 0.8);
    color = vec4(mix(auroraDisplay(result), u_FogColor.rgb, fog), texel.a);
}
