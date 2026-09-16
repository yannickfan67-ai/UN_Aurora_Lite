#version 450
// SPDX-License-Identifier: GPL-3.0-only
#include "shaders/sodium-abi.glsl"
#include "shaders/vegetation-wind.glsl"
layout(location = 0) in uvec2 a_Position;
layout(location = 1) in vec4 a_Color;
layout(location = 2) in uvec2 a_TexCoord;
layout(location = 3) in uvec4 a_LightAndData;
layout(location = 4) in uint a_SulkanMaterial;
uniform sampler2D u_LightTex;
uniform isamplerBuffer u_SectionTimeInfo;
layout(push_constant) uniform PC {
    vec3 u_RegionOffset;
    int u_CurrentTime;
    uint u_RegionID;
};
layout(location = 0) out vec4 auroraTint;
layout(location = 1) out vec2 auroraUv;
layout(location = 2) out vec3 auroraPosition;
layout(location = 3) out vec2 auroraLight;
layout(location = 4) out float auroraFade;
layout(location = 5) flat out uint auroraMaterial;
void main() {
    // Sodium packs each axis into two 10-bit pieces in these two integers.
    uvec3 shifts = uvec3(0u, 10u, 20u);
    uvec3 upper = (uvec3(a_Position.x) >> shifts) & uvec3(1023u);
    uvec3 lower = (uvec3(a_Position.y) >> shifts) & uvec3(1023u);
    vec3 local = vec3((upper << 10u) | lower) * (1.0 / 32768.0) - 8.0;
    uint section = a_LightAndData.w;
    uvec3 sectionXYZ = (uvec3(section) >> uvec3(5u, 0u, 2u)) & uvec3(7u, 3u, 7u);
    vec3 relative = local + vec3(sectionXYZ) * 16.0 + u_RegionOffset;
    // Use the same GPL loader helper as its shadow caster: foliage and shadow agree.
    auroraPosition = relative + sulkanWindOffset(relative, a_SulkanMaterial);
    auroraUv = vec2(a_TexCoord & uvec2(32767u)) * (1.0 / 32768.0)
             + (vec2(a_TexCoord >> 15u) * 2.0 - 1.0) * u_TexCoordShrink;
    auroraTint = a_Color;
    auroraLight = clamp(vec2(a_LightAndData.xy) / 240.0, 0.0, 1.0);
    int started = texelFetch(u_SectionTimeInfo, int(u_RegionID * 256u + section)).r;
    auroraFade = started < 0 ? 1.0 : clamp(float(u_CurrentTime - started) * u_FadePeriodInv, 0.0, 1.0);
    auroraMaterial = a_SulkanMaterial & 65535u;
    gl_Position = u_ProjectionMatrix * u_ModelViewMatrix * vec4(auroraPosition, 1.0);
}
