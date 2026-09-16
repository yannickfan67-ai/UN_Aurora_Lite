// SPDX-License-Identifier: GPL-3.0-only
// UN Aurora Lite — shared Sulkan 0.4.2 interfaces and numeric helpers.
#ifndef AURORA_COMMON
#define AURORA_COMMON
#include "sulkan/frame.glsl"
const vec3 AURORA_LUMA = vec3(0.2126, 0.7152, 0.0722);
vec3 auroraLinear(vec3 value) {
    value = max(value, vec3(0.0));
    return mix(pow((value + 0.055) / 1.055, vec3(2.4)), value / 12.92,
               lessThanEqual(value, vec3(0.04045)));
}
vec3 auroraDisplay(vec3 value) {
    value = max(value, vec3(0.0));
    return mix(1.055 * pow(value, vec3(1.0 / 2.4)) - 0.055, 12.92 * value,
               lessThanEqual(value, vec3(0.0031308)));
}
vec3 auroraHighlightShoulder(vec3 value, float start) {
    value = max(value, vec3(0.0));
    float peak = max(value.r, max(value.g, value.b));
    float excess = max(peak - start, 0.0);
    float room = 1.0 - start;
    float compressed = min(peak, start) + excess * room / (room + excess);
    // Hue-preserving shoulder: no change to midtones, no hard white clipping.
    return value * (compressed / max(peak, 1e-7));
}
vec3 auroraNormalize(vec3 value) {
    return value * inversesqrt(max(dot(value, value), 1e-12));
}
vec3 auroraViewPosition(vec2 coord, float depth) {
    vec4 point = InverseProjection * vec4(coord * 2.0 - 1.0, depth, 1.0);
    float divisor = abs(point.w) < 1e-6 ? (point.w < 0.0 ? -1e-6 : 1e-6) : point.w;
    return point.xyz / divisor;
}
float auroraDay() {
    return smoothstep(-0.10, 0.14, SunDirectionAndRainBrightness.y);
}
bool auroraOverworldAir() {
    return abs(WorldTimeWeatherDimension.w) < 0.5 && CameraPositionHighAndFogType.w < 0.5;
}
vec2 auroraSafeUv(vec2 coord) {
    return clamp(coord, ViewSizeAndInverse.zw * 0.5, vec2(1.0) - ViewSizeAndInverse.zw * 0.5);
}
#endif
