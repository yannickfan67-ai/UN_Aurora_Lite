// SPDX-License-Identifier: GPL-3.0-only
uniform sampler2D Source;
layout(location = 0) in vec2 texCoord;
layout(location = 0) out vec4 color;
void main() {
    vec2 stride = BLUR_DIRECTION / vec2(textureSize(Source, 0));
    vec3 sum = texture(Source, texCoord).rgb * 0.375;
    sum += (texture(Source, texCoord + stride).rgb + texture(Source, texCoord - stride).rgb) * 0.25;
    sum += (texture(Source, texCoord + stride * 2.0).rgb + texture(Source, texCoord - stride * 2.0).rgb) * 0.0625;
    color = vec4(sum, 1.0);
}
