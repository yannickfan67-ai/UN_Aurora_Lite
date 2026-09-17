// SPDX-License-Identifier: GPL-3.0-only
#ifndef AURORA_SHADOWS
#define AURORA_SHADOWS
#include "sulkan/shadows.glsl"

#if SHADOW_QUALITY > 0 && _SULKAN_ENABLED_SHADOW_STRENGTH
#if SHADOW_FILTER > 0
float auroraShadowTap(int cascade, bool entity, vec2 uv, vec2 receiverUv,
                      float depth, vec2 gradient) {
    if (entity) return sulkanEntityBilinearVisibility(cascade, uv, receiverUv, depth, gradient);
    return sulkanShadowBilinearVisibility(cascade, uv, receiverUv, depth, gradient);
}

float auroraShadowFilter(int cascade, bool entity, vec2 uv, float depth, vec2 gradient) {
    vec2 texel = entity ? sulkanEntityShadowTexel(cascade) : sulkanShadowTexel(cascade);
    vec2 radius = texel * float(SHADOW_SOFTNESS);
#if _SULKAN_ENABLED_SHADOW_SOFTNESS
#if SHADOW_FILTER == 1
    // Deterministic bilinear comparisons: no frame-dependent rotation or grain.
    float visible = auroraShadowTap(cascade, entity, uv + vec2(-radius.x, -radius.y), uv, depth, gradient);
    visible += auroraShadowTap(cascade, entity, uv + vec2(radius.x, -radius.y), uv, depth, gradient);
    visible += auroraShadowTap(cascade, entity, uv + vec2(-radius.x, radius.y), uv, depth, gradient);
    visible += auroraShadowTap(cascade, entity, uv + radius, uv, depth, gradient);
    return visible * 0.25;
#else
    // A separable tent: center 4, axis taps 2, corners 1 (total 16).
    float visible = 0.0;
    for (int y = -1; y <= 1; ++y) for (int x = -1; x <= 1; ++x) {
        float weight = float((x == 0 ? 2 : 1) * (y == 0 ? 2 : 1));
        visible += auroraShadowTap(cascade, entity, uv + vec2(x, y) * radius, uv, depth, gradient) * weight;
    }
    return visible / 16.0;
#endif
#else
    return auroraShadowTap(cascade, entity, uv, uv, depth, gradient);
#endif
}

float auroraShadowCascade(int cascade, vec3 position, vec3 normal) {
    vec3 coord = sulkanShadowCoord(cascade, position + normal * sulkanShadowNormalOffset(cascade, normal));
    vec2 terrainTexel = sulkanShadowTexel(cascade);
    vec2 entityTexel = cascade < 2 ? sulkanEntityShadowTexel(cascade) : vec2(0.0);
    // Keep the full PCF footprint inside the map, including the gather's edge.
    vec2 guard = max(terrainTexel, entityTexel) * (float(SHADOW_SOFTNESS) + 1.5);
    if (any(lessThanEqual(coord.xy, guard)) || any(greaterThanEqual(coord.xy, vec2(1.0) - guard))
        || coord.z <= 0.0 || coord.z >= 1.0) return 1.0;
    float texelWorld = max(CascadeParams[cascade].x, 0.0001);
    float bias = (0.0005 + texelWorld * 0.015) / max(CascadeParams[cascade].w, 1.0);
    vec2 gradient = sulkanReceiverDepthGradient(cascade, normal);
    float terrain = auroraShadowFilter(cascade, false, coord.xy, coord.z - bias, gradient);
    float entity = cascade < 2 ? auroraShadowFilter(cascade, true, coord.xy, coord.z - bias, gradient) : 1.0;
    return min(terrain, entity);
}

float auroraCastShadow(vec3 position, vec3 normal) {
    float distanceToEye = length(position);
    int last = sulkanLastCascade();
    if (!sulkanCascadeActive(last) || distanceToEye >= CascadeParams[last].z) return 1.0;
    int current = sulkanSelectCascade(distanceToEye);
    float visible = auroraShadowCascade(current, position, normal);
    if (current == last) {
        float fadeStart = mix(CascadeParams[last].y, CascadeParams[last].z, 0.82);
        return mix(visible, 1.0, smoothstep(fadeStart, CascadeParams[last].z, distanceToEye));
    }
    int next = current + 1;
    while (next < last && !sulkanCascadeActive(next)) ++next;
    // Release 0.4.2 fits the next cascade from 0.82 * the previous split.
    // Start beyond 0.84 * split to keep this wider blend inside that overlap.
    float blendStart = max(mix(CascadeParams[current].y, CascadeParams[current].z, 0.82),
                           CascadeParams[current].z * 0.84);
    float blend = smoothstep(blendStart, CascadeParams[current].z, distanceToEye);
    if (blend <= 0.0) return visible;
    return mix(visible, auroraShadowCascade(next, position, normal), blend);
}
#endif
#endif

float auroraShadowVisibility(vec3 position, vec3 normal) {
#if SHADOW_QUALITY > 0 && _SULKAN_ENABLED_SHADOW_STRENGTH
    if (abs(WorldTimeWeatherDimension.w) > 0.5 || ShadowParams.x <= 0.0) return 1.0;
#if SHADOW_FILTER == 0
    float visible = sulkanCastShadowVisibility(position, normal);
#else
    float visible = auroraCastShadow(position, normal);
#endif
    // Applied to direct illumination only; ambient and block light retain their energy.
    return mix(1.0, visible, clamp(ShadowParams.x * float(SHADOW_STRENGTH), 0.0, 1.0));
#else
    return 1.0;
#endif
}
#endif
