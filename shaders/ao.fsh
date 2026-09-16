#version 450
// SPDX-License-Identifier: GPL-3.0-only
#include "shaders/common.glsl"
uniform sampler2D Depth;
layout(location = 0) in vec2 texCoord;
layout(location = 0) out vec2 occlusionAndDistance;
void main() {
    float depth = texture(Depth, texCoord).r;
    if (depth <= 1e-7) { occlusionAndDistance = vec2(1.0, 0.0); return; }
    vec3 p = auroraViewPosition(texCoord, depth);
    float distanceToEye = length(p);
    if (distanceToEye >= 96.0) {
        occlusionAndDistance = vec2(1.0, min(distanceToEye, 60000.0));
        return;
    }
    vec2 fullPixel = ViewSizeAndInverse.zw;
    vec3 px = auroraViewPosition(auroraSafeUv(texCoord + vec2(fullPixel.x, 0.0)), texture(Depth, auroraSafeUv(texCoord + vec2(fullPixel.x, 0.0))).r);
    vec3 mx = auroraViewPosition(auroraSafeUv(texCoord - vec2(fullPixel.x, 0.0)), texture(Depth, auroraSafeUv(texCoord - vec2(fullPixel.x, 0.0))).r);
    vec3 py = auroraViewPosition(auroraSafeUv(texCoord + vec2(0.0, fullPixel.y)), texture(Depth, auroraSafeUv(texCoord + vec2(0.0, fullPixel.y))).r);
    vec3 my = auroraViewPosition(auroraSafeUv(texCoord - vec2(0.0, fullPixel.y)), texture(Depth, auroraSafeUv(texCoord - vec2(0.0, fullPixel.y))).r);
    vec3 dx = abs(px.z - p.z) < abs(p.z - mx.z) ? px - p : p - mx;
    vec3 dy = abs(py.z - p.z) < abs(p.z - my.z) ? py - p : p - my;
    vec3 n = auroraNormalize(cross(dx, dy));
    n *= dot(n, -p) < 0.0 ? -1.0 : 1.0;
    float radius = 0.9;
    vec2 screenRadius = vec2(abs(Projection[0][0]), abs(Projection[1][1])) * radius / max(abs(p.z), 0.5) * 0.5;
#if AO_QUALITY >= 2
    const int sampleCount = 8;
#else
    const int sampleCount = 4;
#endif
    float blocked = 0.0;
    float count = 0.0;
    for (int i = 0; i < sampleCount; ++i) {
        float angle = (float(i) + 0.375) * (6.28318530718 / float(sampleCount));
        vec2 offset = vec2(cos(angle), sin(angle)) * screenRadius * (0.48 + 0.45 * float(i % 2));
        vec2 qUv = texCoord + offset;
        if (any(lessThan(qUv, fullPixel)) || any(greaterThan(qUv, vec2(1.0) - fullPixel))) continue;
        float qDepth = texture(Depth, qUv).r;
        if (qDepth <= 1e-7) continue;
        vec3 delta = auroraViewPosition(qUv, qDepth) - p;
        float separation = length(delta);
        float facing = max(dot(n, delta) / max(separation, 0.001) - 0.14, 0.0);
        blocked += facing * (1.0 - smoothstep(0.12, radius * 1.5, separation));
        count += 1.0;
    }
    float ao = clamp(1.0 - blocked / max(count, 1.0) * float(AO_STRENGTH) * 2.4, 0.4, 1.0);
    occlusionAndDistance = vec2(mix(ao, 1.0, smoothstep(56.0, 96.0, distanceToEye)), min(distanceToEye, 60000.0));
}
