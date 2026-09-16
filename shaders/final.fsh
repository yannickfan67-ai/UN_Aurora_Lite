#version 450
// SPDX-License-Identifier: GPL-3.0-only
#include "shaders/common.glsl"
uniform sampler2D Source;
#if _SULKAN_ENABLED_BLOOM_STRENGTH
uniform sampler2D Bloom;
#endif
#if _SULKAN_ENABLED_BLOOM_STRENGTH || EDGE_SMOOTHING == 1
uniform sampler2D HandDepth;
#endif
layout(location = 0) in vec2 texCoord;
layout(location = 0) out vec4 color;
void main() {
    vec3 result = texture(Source, texCoord).rgb;
#if _SULKAN_ENABLED_BLOOM_STRENGTH || EDGE_SMOOTHING == 1
    float worldEffect = texture(HandDepth, texCoord).r > 1e-7 ? 0.0 : 1.0;
#endif
#if EDGE_SMOOTHING == 1
    vec2 pixel = 1.0 / vec2(textureSize(Source, 0));
    vec3 east = texture(Source, texCoord + vec2(pixel.x, 0.0)).rgb;
    vec3 west = texture(Source, texCoord - vec2(pixel.x, 0.0)).rgb;
    vec3 north = texture(Source, texCoord + vec2(0.0, pixel.y)).rgb;
    vec3 south = texture(Source, texCoord - vec2(0.0, pixel.y)).rgb;
    float horizontal = abs(dot(east - west, AURORA_LUMA));
    float vertical = abs(dot(north - south, AURORA_LUMA));
    float edge = smoothstep(0.06, 0.3, max(horizontal, vertical));
    vec3 neighborhood = horizontal > vertical ? (north + south) * 0.5 : (east + west) * 0.5;
    result = mix(result, neighborhood, edge * 0.20 * worldEffect);
#endif
#if _SULKAN_ENABLED_BLOOM_STRENGTH
    result += texture(Bloom, texCoord).rgb * float(BLOOM_STRENGTH) * worldEffect;
#endif
    result *= float(EXPOSURE);
    result = auroraHighlightShoulder(result, 0.9);
    result = auroraDisplay(result);
    float light = dot(result, AURORA_LUMA);
    result = clamp(mix(vec3(light), result, float(SATURATION)), 0.0, 1.0);
    // Endpoint-preserving contrast keeps near-black values distinct instead of
    // subtracting a fixed black offset from every dark pixel.
    result += (float(CONTRAST) - 1.0) * 2.0 * result * (1.0 - result) * (2.0 * result - 1.0);
#if DITHERING == 1
    // Static, sub-code-value noise reduces 8-bit fog/sky banding without
    // animated grain. Fade at the endpoints to retain true black and white.
    float noise = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5;
    vec3 endpoint = smoothstep(vec3(0.0), vec3(1.0 / 255.0), min(result, vec3(1.0) - result));
    result += noise * (1.0 / 255.0) * endpoint;
#endif
    color = vec4(clamp(result, 0.0, 1.0), 1.0);
}
