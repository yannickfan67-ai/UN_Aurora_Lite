#version 450
// SPDX-License-Identifier: GPL-3.0-only
#include "shaders/common.glsl"
uniform sampler2D Source;
uniform sampler2D HandDepth;
layout(location = 0) in vec2 texCoord;
layout(location = 0) out vec4 color;
void main() {
    vec2 stepUv = 1.0 / vec2(textureSize(Source, 0));
    vec3 sum = vec3(0.0);
    for (int y = -1; y <= 1; y += 2) for (int x = -1; x <= 1; x += 2) {
        vec2 sampleUv = auroraSafeUv(texCoord + vec2(x, y) * stepUv);
        vec3 sampleColor = texture(Source, sampleUv).rgb;
        // Match all four texels in Source's bilinear footprint. Masking only
        // the final output pixel lets a bright held block bloom onto the world.
        vec4 hand = textureGather(HandDepth, sampleUv);
        if (any(greaterThan(hand, vec4(1e-7)))) sampleColor = vec3(0.0);
        float brightness = dot(sampleColor, AURORA_LUMA);
        float keep = smoothstep(float(BLOOM_THRESHOLD) - 0.10, float(BLOOM_THRESHOLD) + 0.10, brightness);
        sum += sampleColor * keep;
    }
    color = vec4(sum * 0.25, 1.0);
}
