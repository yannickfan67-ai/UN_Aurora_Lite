#version 450
// SPDX-License-Identifier: GPL-3.0-only
// Diagnostic only: the production graph never schedules this entrypoint.
#include "shaders/common.glsl"
#include "shaders/shadows.glsl"
uniform sampler2D ProbePosition;
uniform sampler2D ProbeNormal;
layout(location = 0) in vec2 texCoord;
layout(location = 0) out vec4 color;
void main() {
    vec3 position = texture(ProbePosition, texCoord).xyz;
    vec3 normal = auroraNormalize(texture(ProbeNormal, texCoord).xyz);
    float visibility = auroraShadowVisibility(position, normal);
    color = vec4(vec3(visibility), 1.0);
}
