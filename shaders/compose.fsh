#version 450
// SPDX-License-Identifier: GPL-3.0-only
#include "shaders/common.glsl"
#include "shaders/atmosphere.glsl"
uniform sampler2D Scene;
uniform sampler2D Depth;
uniform sampler2D HandDepth;
#if _SULKAN_ENABLED_AO_QUALITY && _SULKAN_ENABLED_AO_STRENGTH
uniform sampler2D Ambient;
#endif
layout(location = 0) in vec2 texCoord;
layout(location = 0) out vec4 sceneLinear;
void main() {
    vec3 result = auroraLinear(texture(Scene, texCoord).rgb);
    float depth = texture(Depth, texCoord).r;
    bool hand = texture(HandDepth, texCoord).r > 1e-7;
    if (!hand && depth > 1e-7) {
        vec3 p = auroraViewPosition(texCoord, depth);
        float distanceToEye = length(p);
#if _SULKAN_ENABLED_AO_QUALITY && _SULKAN_ENABLED_AO_STRENGTH
        // Four-tap bilateral upsampling rejects samples across depth boundaries.
        ivec2 size = textureSize(Ambient, 0);
        vec2 pixel = texCoord * vec2(size) - 0.5;
        ivec2 corner = ivec2(floor(pixel));
        vec2 fraction = fract(pixel);
        float total = 0.0;
        float weightSum = 0.0;
        for (int y = 0; y < 2; ++y) for (int x = 0; x < 2; ++x) {
            vec2 tap = texelFetch(Ambient, clamp(corner + ivec2(x, y), ivec2(0), size - 1), 0).rg;
            vec2 weights = mix(vec2(1.0) - fraction, fraction, vec2(x, y));
            float weight = weights.x * weights.y * exp(-abs(tap.y - distanceToEye) / max(0.2, distanceToEye * 0.012));
            if (tap.y <= 0.0) weight = 0.0;
            total += tap.x * weight;
            weightSum += weight;
        }
        float contactVisibility = weightSum > 1e-4 ? total / weightSum : 1.0;
        float darkDetail = smoothstep(0.01, 0.08, dot(result, AURORA_LUMA));
        result *= mix(1.0, contactVisibility, 0.25 + 0.75 * darkDetail);
#endif
        if (auroraOverworldAir()) {
            vec3 worldRay = auroraNormalize(mat3(InverseView) * p);
            float rain = clamp(WorldTimeWeatherDimension.y, 0.0, 1.0);
            float horizon = 1.0 - smoothstep(0.02, 0.7, abs(worldRay.y));
            float opticalDepth = max(distanceToEye - 20.0, 0.0) * (0.0007 + 0.0012 * rain);
            float haze = min(1.0 - exp(-opticalDepth * float(FOG_STRENGTH)), 0.22) * horizon;
#if _SULKAN_ENABLED_HEIGHT_FOG
            // Combine transmittances and cap the total so distant detail stays readable.
            haze = min(1.0 - (1.0 - haze) * (1.0 - auroraHeightMist(worldRay, distanceToEye)), 0.28);
#endif
            // Avoid laying bright Overworld fog over otherwise unlit tunnels.
            haze *= smoothstep(0.015, 0.12, dot(result, AURORA_LUMA));
            vec3 fog = auroraLinear(max(FogColorAndStart.rgb, vec3(0.0)));
#if _SULKAN_ENABLED_SUNSET_GLOW
            fog += auroraSunsetScatter(worldRay) * 0.5;
#endif
            result = mix(result, fog, haze);
        }
    }
#if _SULKAN_ENABLED_SUNSET_GLOW
    if (!hand && depth <= 1e-7 && auroraOverworldAir()) {
        // Use a finite reversed-Z depth to reconstruct a sky ray, never infinity.
        vec3 worldRay = auroraNormalize(mat3(InverseView) * auroraViewPosition(texCoord, 0.5));
        float skyVisibility = smoothstep(0.002, 0.04, dot(result, AURORA_LUMA));
        result += auroraSunsetScatter(worldRay) * skyVisibility * (vec3(1.0) - clamp(result, 0.0, 1.0));
    }
#endif
    sceneLinear = vec4(max(result, vec3(0.0)), 1.0);
}
