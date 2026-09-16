// SPDX-License-Identifier: GPL-3.0-only
#ifndef AURORA_ATMOSPHERE
#define AURORA_ATMOSPHERE

float auroraTwilight() {
    float elevation = SunDirectionAndRainBrightness.y;
    return smoothstep(-0.14, 0.015, elevation)
         * (1.0 - smoothstep(0.15, 0.45, elevation));
}

#if _SULKAN_ENABLED_SUNSET_GLOW
vec3 auroraSunsetScatter(vec3 worldRay) {
    float towardSun = max(dot(worldRay, auroraNormalize(SunDirectionAndRainBrightness.xyz)), 0.0);
    float horizon = (1.0 - smoothstep(0.10, 0.70, abs(worldRay.y)))
                  * smoothstep(-0.12, 0.02, worldRay.y);
    float rain = clamp(WorldTimeWeatherDimension.y, 0.0, 1.0);
    // A broad, directional tint over the existing sky; no replacement sun disc.
    float glow = pow(towardSun, 6.0) * horizon * auroraTwilight()
               * (1.0 - 0.90 * rain) * float(SUNSET_GLOW);
    return vec3(0.22, 0.065, 0.014) * glow;
}
#endif

#if _SULKAN_ENABLED_HEIGHT_FOG
float auroraMistDensity(float height) {
    float relativeHeight = height - float(FOG_HEIGHT);
    // The lower fade protects deep underground scenes. The upper falloff gives
    // valleys more mist than peaks, with a user-adjustable reference altitude.
    return smoothstep(-32.0, -8.0, relativeHeight)
         * exp2(-max(relativeHeight, 0.0) * 0.075);
}

float auroraHeightMist(vec3 worldRay, float distanceToEye) {
    float endDistance = min(distanceToEye, 256.0);
    if (endDistance <= 24.0) return 0.0;
    float cameraHeight = CameraPositionHighAndFogType.y + CameraPositionLowAndFarPlane.y;
    float startHeight = cameraHeight + worldRay.y * 24.0;
    float endHeight = cameraHeight + worldRay.y * endDistance;
    // Three arithmetic samples approximate density along the ray. No depth
    // taps, temporal history, or light/shadow ray marching are required.
    float density = (auroraMistDensity(startHeight)
                   + 4.0 * auroraMistDensity((startHeight + endHeight) * 0.5)
                   + auroraMistDensity(endHeight)) / 6.0;
    float rain = clamp(WorldTimeWeatherDimension.y, 0.0, 1.0);
    float weather = 0.22 + 0.78 * max(auroraTwilight(), rain);
    float opticalDepth = (endDistance - 24.0) * density * weather * 0.004 * float(HEIGHT_FOG);
    return min(1.0 - exp(-opticalDepth), 0.22);
}
#endif
#endif
