#!/usr/bin/env python3
"""Render synthetic fixtures with already-compiled post shaders on a Vulkan device.

Requires NumPy, the compiled NativeRenderProbe, and a Vulkan ICD (e.g. lavapipe).
The fixture images are diagnostics, not Minecraft screenshots or FPS benchmarks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--java', default='java')
    parser.add_argument('--classpath', required=True)
    args = parser.parse_args()
    folder = args.folder.resolve()
    output = folder / 'pixels'
    output.mkdir(parents=True, exist_ok=True)
    modules = json.loads((folder / 'native-compile.json').read_text())['modules']
    rows = json.loads((folder / 'loader-probe.json').read_text())['shaders']
    vertex = next(m['spirv'] for m in modules if m['entry'] == 'fullscreen.vert')
    width = height = 128
    frame = np.zeros(656 // 4, dtype='<f4')
    for offset in (0, 64, 128, 192, 256, 320, 576):
        frame[offset//4:offset//4+16] = np.eye(4, dtype='<f4').ravel()
    # Reversed-Z projection with a 0.1 near plane; matrix storage is column-major.
    projection = np.array([[1,0,0,0],[0,1,0,0],[0,0,0,.1],[0,0,-1,0]], dtype='<f4')
    frame[0:16] = projection.T.ravel()
    frame[32:48] = np.linalg.inv(projection).T.ravel()
    frame[416//4:432//4] = (width, height, 1/width, 1/height)
    frame[448//4:464//4] = (.6, .8, 0, 1)
    frame[464//4:480//4] = (-.6, -.8, 0, 0)
    frame[496//4+3] = 256
    frame_path = output / 'frame.bin'
    frame.tofile(frame_path)

    def rgba(value=0):
        pixels = np.full((height, width, 4), value, dtype='<f4')
        pixels[:,:,3] = 1
        return pixels

    inputs = {}

    def texture(name, pixels, linear=False):
        path = output / (name+'.f32')
        np.asarray(pixels, dtype='<f4').tofile(path)
        inputs[name] = dict(path=str(path), width=pixels.shape[1], height=pixels.shape[0], linear=linear)
        return inputs[name]

    black = rgba()
    hand = rgba()
    hand[29:98,43:86,0] = .7
    held_white = rgba()
    held_white[29:98,43:86,:3] = 1
    scene = rgba()
    scene[:,:,:3] = np.linspace(0,.04,width, dtype='<f4')[None,:,None]
    scene[height//2:,:,:3] = (.12,.28,.5)
    scene[:8,:8,:3] = 0
    bloom = rgba(.65)
    bloom[:16,:16,:3] = 0
    texture('black', black)
    texture('scene', scene, True)
    texture('bloom', bloom, True)
    texture('hand', hand)
    texture('held-white', held_white, True)
    texture('flat-depth', rgba(.1 / 4))
    texture('far-depth', rgba(.1 / 200))
    jobs = []

    def job(name, scenario, entry, textures, size=(width,height), unorm=True, frame_file=frame_path):
        module = next(m for m in modules if m['case']==scenario and m['entry']==entry and m['variant']=='base')
        row = next(r for r in rows if r['case']==scenario and r['entry']==entry)
        # NativeCompileProbe.rebind assigns UBO 0 followed by sorted read names.
        # Its unused shadow bindings sort after these post-process sampler names.
        assert set(textures) == set(row['reads']), (name, textures, row['reads'])
        jobs.append(dict(name=name, width=size[0], height=size[1], unorm=unorm,
                         frame=str(frame_file), vertex=str(Path(vertex).resolve()),
                         fragment=str(Path(module['spirv']).resolve()),
                         textures=[inputs[textures[n]] for n in sorted(textures)],
                         output=str(output/(name+('.rgba8' if unorm else '.f32')))))

    final = dict(Source='scene', Bloom='bloom', HandDepth='hand')
    job('final', 'default', 'shaders/final.fsh', final)
    job('final-repeat', 'default', 'shaders/final.fsh', final)
    job('final-no-dither', 'dithering-off', 'shaders/final.fsh', final)
    job('final-no-bloom', 'bloom-disabled', 'shaders/final.fsh', dict(Source='scene'))
    job('bloom-hand', 'default', 'shaders/bloom-seed.fsh', dict(Source='held-white', HandDepth='hand'), (32,32), False)
    job('bloom-world', 'default', 'shaders/bloom-seed.fsh', dict(Source='held-white', HandDepth='black'), (32,32), False)
    for name in ('flat','far'):
        job('ao-'+name, 'default', 'shaders/ao.fsh', dict(Depth=name+'-depth'), (64,64), False)
    job('ao-sky', 'default', 'shaders/ao.fsh', dict(Depth='black'), (64,64), False)

    # Exercise the actual compose SPIR-V with independent sky/geometry fixtures.
    # The off variant is an identity in linear space (legacy haze and AO are off).
    atmosphere_scene = rgba()
    atmosphere_scene[:,:,:3] = (.32, .38, .46)
    texture('atmosphere-scene', atmosphere_scene)
    texture('dark-interior', rgba(.015))
    texture('mist-depth', rgba(.1 / 160))
    texture('weather-depth', rgba(.1 / 72))
    texture('near-depth', rgba(.1 / 4))

    def atmosphere_frame(name, height=64, elevation=.05, rain=0, dimension=0, fog_type=0, away=False):
        state = frame.copy()
        state[432//4:448//4] = (0, rain, 0, dimension)
        state[448//4:464//4] = (0, elevation, (1 if away else -1)*np.sqrt(max(0,1-elevation**2)), 1-rain)
        state[480//4:496//4] = (0, height, 0, fog_type)
        state[512//4:528//4] = (.7, .75, .8, 0)
        path = output / ('frame-'+name+'.bin')
        state.tofile(path)
        return path

    atmospheres = {}

    def atmosphere_pair(name, depth='mist-depth', source='atmosphere-scene', **environment):
        state = atmosphere_frame(name, **environment)
        atmospheres[name] = state
        for suffix in ('on','off'):
            job(name+'-'+suffix, 'atmosphere-test-'+suffix, 'shaders/compose.fsh',
                dict(Scene=source, Depth=depth, HandDepth='hand'), unorm=False, frame_file=state)

    atmosphere_pair('sky-twilight', depth='black')
    atmosphere_pair('sky-away', depth='black', away=True)
    atmosphere_pair('sky-noon', depth='black', elevation=1)
    atmosphere_pair('sky-night', depth='black', elevation=-1)
    atmosphere_pair('sky-rain', depth='black', rain=1)
    atmosphere_pair('mist-twilight')
    # Keep the weather comparison below the far-fog opacity cap.
    atmosphere_pair('mist-noon', depth='weather-depth', elevation=1)
    atmosphere_pair('mist-rain', depth='weather-depth', elevation=1, rain=1)
    atmosphere_pair('mist-near', depth='near-depth')
    atmosphere_pair('mist-high', height=512)
    atmosphere_pair('mist-underground', height=-512)
    atmosphere_pair('mist-dark', source='dark-interior')
    atmosphere_pair('mist-raised', height=128)
    job('mist-raised-reference', 'atmosphere-test-raised', 'shaders/compose.fsh',
        dict(Scene='atmosphere-scene', Depth='mist-depth', HandDepth='hand'),
        unorm=False, frame_file=atmospheres['mist-raised'])
    # Each fixture has sky on one half and geometry on the other half.
    mixed_depth = rgba(.1 / 160)
    mixed_depth[:height//2,:,0] = 0
    texture('mixed-depth', mixed_depth)
    neutral_ao = rgba()
    neutral_ao[:,:,0] = 1
    neutral_ao[:,:,1] = 160
    texture('neutral-ao', neutral_ao)
    for suffix, scenario in [('on','default'), ('off','atmosphere-off')]:
        job('atmosphere-default-'+suffix, scenario, 'shaders/compose.fsh',
            dict(Scene='atmosphere-scene', Depth='mixed-depth', HandDepth='hand', Ambient='neutral-ao'),
            unorm=False, frame_file=atmospheres['mist-twilight'])
    for name, environment in [('nether',dict(dimension=-1)), ('end',dict(dimension=1)),
                              ('custom-dimension',dict(dimension=2)), ('water',dict(fog_type=1)),
                              ('lava',dict(fog_type=2)), ('powder-snow',dict(fog_type=3))]:
        atmosphere_pair(name, depth='mixed-depth', **environment)
    config = output / 'jobs.json'
    config.write_text(json.dumps({'jobs':jobs}, indent=2)+'\n')
    subprocess.run([args.java,'--enable-native-access=ALL-UNNAMED','-cp',args.classpath,
                    'NativeRenderProbe',str(config)], check=True)
    rendered = {}
    for j in jobs:
        p = np.fromfile(j['output'], dtype='u1' if j['unorm'] else '<f4').reshape(j['height'],j['width'],4)
        assert np.isfinite(p).all(), j['name']
        rendered[j['name']] = p
    result = rendered['final']
    assert np.array_equal(result,rendered['final-repeat']), 'Dither changes between identical frames'
    assert np.max(abs(result.astype(int)-rendered['final-no-dither'].astype(int)))<=1, 'Dither exceeds one 8-bit code value'
    assert np.any(result!=rendered['final-no-dither']), 'Dither had no observable effect'
    assert not np.any(result[:8,:8,:3]), 'Black endpoints were lifted'
    hand_mask = hand[:,:,0] > 0
    assert np.array_equal(result[hand_mask],rendered['final-no-bloom'][hand_mask]), 'Bloom changed held-item pixels'
    assert np.mean(result[100:,90:,:3].astype(int)-rendered['final-no-bloom'][100:,90:,:3].astype(int))>0, 'World bloom is absent'
    assert np.max(np.abs(rendered['bloom-hand'][:,:,:3]))<1e-7, 'Held-item light leaked into bloom extraction'
    assert rendered['bloom-world'][:,:,:3].max()>.5, 'The same bright world block should bloom'
    for name in ('ao-flat','ao-far','ao-sky'):
        assert np.allclose(rendered[name][:,:,0],1,atol=1e-6), 'Unexpected AO on '+name
    assert np.all(rendered['ao-far'][:,:,1]>96), 'Far AO test did not reach the early-out range'
    checks = dict(finitePixels='PASS', stableDither='PASS', ditherAtMostOneCodeValue='PASS',
                  blackPreserved='PASS', heldItemOutputProtected='PASS', heldItemBloomSourceExcluded='PASS',
                  worldBloomStillVisible='PASS', flatFarSkyAo='PASS')
    expected_linear = np.where(atmosphere_scene[:,:,:3] <= .04045,
                               atmosphere_scene[:,:,:3] / 12.92,
                               ((atmosphere_scene[:,:,:3]+.055)/1.055)**2.4)
    assert np.allclose(rendered['mist-twilight-off'][:,:,:3], expected_linear, atol=1e-6), 'Disabled atmosphere is not identity'
    for name in atmospheres:
        assert np.array_equal(rendered[name+'-on'][hand_mask],rendered[name+'-off'][hand_mask]), name+' changed held items'

    def delta(name):
        return rendered[name+'-on'][:,:,:3] - rendered[name+'-off'][:,:,:3]

    # Narrow horizon strip avoids comparing differing ray elevations; exclude hand.
    horizon_mask = np.zeros((height,width), dtype=bool)
    horizon_mask[60:68] = True
    horizon_mask &= ~hand_mask
    for name in ('sky-noon','sky-night','sky-away','mist-near','mist-high','mist-underground','mist-dark',
                 'nether','end','custom-dimension','water','lava','powder-snow'):
        assert np.max(np.abs(delta(name))) < 1e-6, 'Atmosphere exclusion failed: '+name
    glow = delta('sky-twilight')[horizon_mask].mean(axis=0)
    assert glow[0] > .01 and glow[0] > 2*glow[1] > 2*glow[2], 'Twilight sky glow is absent or not warm'
    assert delta('sky-rain')[horizon_mask].mean() < delta('sky-twilight')[horizon_mask].mean()*.2, 'Rain should suppress sunset glow'
    assert delta('mist-twilight')[horizon_mask].mean() > .015, 'Low-altitude mist is absent'
    assert delta('mist-rain')[horizon_mask].mean() > delta('mist-noon')[horizon_mask].mean()*2, 'Rain should strengthen height mist'
    raised_delta = rendered['mist-raised-reference'][:,:,:3] - rendered['mist-raised-off'][:,:,:3]
    assert raised_delta[horizon_mask].mean() > delta('mist-raised')[horizon_mask].mean()*3, 'Reference altitude has no effect'
    # Recover opacity using blue (glow contributes positively): it must stay below
    # the combined 0.28 limit, preserving at least 72% of the source detail.
    fog_linear = ((np.array([.7,.75,.8])+.055)/1.055)**2.4
    assert np.max(delta('mist-twilight')[:,:,2]/(fog_linear[2]-expected_linear[:,:,2])) < .29, 'Mist obscures too much detail'
    default_delta = delta('atmosphere-default')
    assert np.max(np.abs(default_delta[hand_mask])) == 0, 'Default atmosphere changed held items'
    assert np.max(default_delta[:64,:,0]) > .01, 'Default sunset setting has no observable effect'
    assert .005 < default_delta[64:,:,2].max() < .08, 'Default mist is absent or excessive'
    checks.update(atmosphereOffIdentity='PASS', atmosphereHeldItems='PASS',
                  directionalWarmTwilight='PASS', sunsetRainAttenuation='PASS',
                  heightMistWeatherResponse='PASS', adjustableMistAltitude='PASS',
                  atmosphereEnvironmentExclusions='PASS', nearDarkHighUndergroundProtection='PASS',
                  boundedAtmosphereOpacity='PASS', balancedAtmosphereDefaults='PASS')
    report = json.loads((output/'vulkan-render.json').read_text())
    report['checks'] = checks
    report['outputSha256'] = {j['name']:hashlib.sha256(Path(j['output']).read_bytes()).hexdigest() for j in jobs}
    report['testedSpirvSha256'] = {str(Path(j['fragment']).name):hashlib.sha256(Path(j['fragment']).read_bytes()).hexdigest() for j in jobs}
    report['fixtureResolution'] = [width,height]
    report['limitations'] = ['Synthetic post-process inputs only; no Minecraft world or terrain draw.',
                             'Float fixtures use RGBA32_FLOAT; final output uses the pack RGBA8_UNORM format.',
                             'No hardware FPS or real GPU driver compatibility measurement.']
    (folder/'render-checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
