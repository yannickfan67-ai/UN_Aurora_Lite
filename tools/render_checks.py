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

    def job(name, scenario, entry, textures, size=(width,height), unorm=True):
        module = next(m for m in modules if m['case']==scenario and m['entry']==entry and m['variant']=='base')
        row = next(r for r in rows if r['case']==scenario and r['entry']==entry)
        # NativeCompileProbe.rebind assigns UBO 0 followed by sorted read names.
        # Its unused shadow bindings sort after these post-process sampler names.
        assert set(textures) == set(row['reads']), (name, textures, row['reads'])
        jobs.append(dict(name=name, width=size[0], height=size[1], unorm=unorm,
                         frame=str(frame_path), vertex=str(Path(vertex).resolve()),
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
