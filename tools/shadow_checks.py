#!/usr/bin/env python3
"""Render the production shadow helper against synthetic occluder/depth fixtures.

This tests receiver sampling, not Minecraft's production of terrain/entity maps.
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
    output = folder/'shadow-pixels'
    output.mkdir(parents=True, exist_ok=True)
    modules = json.loads((folder/'native-compile.json').read_text())['modules']
    vertex = next(m['spirv'] for m in modules if m['entry']=='fullscreen.vert')
    width = height = 128
    map_size = 64
    inputs = {}

    def rgba(size, rgb=0):
        pixels = np.zeros((size,size,4),dtype='<f4')
        pixels[:,:,:3] = rgb
        pixels[:,:,3] = 1
        return pixels

    def texture(name, pixels):
        path = output/(name+'.f32')
        np.asarray(pixels,dtype='<f4').tofile(path)
        inputs[name] = dict(path=str(path),width=pixels.shape[1],height=pixels.shape[0],linear=False)

    coordinates = ((np.arange(width)+.5)/width-.5)*24
    px,py = np.meshgrid(coordinates,coordinates)
    positions = rgba(width)
    positions[:,:,0] = px
    positions[:,:,1] = py
    texture('positions',positions)
    texture('normal',rgba(width,(0,0,1)))
    texture('clear',rgba(map_size,1))
    texture('blocked',rgba(map_size,.25))
    diagonal = rgba(map_size,1)
    mx,my = np.meshgrid(np.arange(map_size)+.5,np.arange(map_size)+.5)
    diagonal[mx+.35*my>map_size*.66,:3] = .25
    texture('diagonal',diagonal)

    frame = np.zeros(656//4,dtype='<f4')
    for offset in (0,64,128,192,256,320,576):
        frame[offset//4:offset//4+16] = np.eye(4,dtype='<f4').ravel()
    frame[416//4:432//4] = (width,height,1/width,1/height)
    frame[448//4:464//4] = (0,0,1,1)
    frame_paths = {}
    for name,dimension,time in [('normal',0,0),('later',0,123),('nether',-1,0),('end',1,0)]:
        f = frame.copy()
        f[432//4+3] = dimension
        f[400//4] = time
        path = output/('frame-'+name+'.bin')
        f.tofile(path)
        frame_paths[name] = str(path)

    def shadow_data(name, splits=(64,), enabled=.92, active=None):
        # Release UBO: 4 matrices, 4 params, light direction, global params,
        # followed by an extra native inverse-view matrix unused by the include.
        state = np.zeros(416//4,dtype='<f4')
        matrix = np.eye(4,dtype='<f4')
        matrix[0,0] = matrix[1,1] = 1/16
        matrix[2,2] = -1/256
        matrix[2,3] = .5
        active = list(range(len(splits))) if active is None else active
        start = 0
        for cascade in range(4):
            state[cascade*16:cascade*16+16] = matrix.T.ravel()
            if cascade in active:
                end = splits[active.index(cascade)]
                state[64+cascade*4:68+cascade*4] = (.5,start,end,256)
                start = end
        state[80:84] = (0,0,1,0)
        state[84:88] = (enabled,0,.3,4)
        state[88:104] = np.eye(4,dtype='<f4').ravel()
        path = output/('shadow-'+name+'.bin')
        state.tofile(path)
        return str(path)

    normal_shadow = shadow_data('single')
    jobs = []

    def job(name, case='default', terrain='diagonal', entity='clear', position='positions',
            normal='normal', frame_name='normal', shadow=normal_shadow, cascade_maps=None):
        module = next(m for m in modules if m['case']==case and m['entry']=='tools/shadow-probe.fsh')
        textures = dict(ProbePosition=position,ProbeNormal=normal,
                        SulkanEntityShadowMap0=entity,SulkanEntityShadowMap1=entity)
        for cascade in range(4):
            textures['SulkanShadowMap'+str(cascade)] = (cascade_maps or {}).get(cascade,terrain)
        jobs.append(dict(name=name,width=width,height=height,unorm=False,
                         uniforms=[frame_paths[frame_name],shadow],
                         vertex=str(Path(vertex).resolve()),fragment=str(Path(module['spirv']).resolve()),
                         textures=[inputs[textures[n]] for n in sorted(textures)],
                         output=str(output/(name+'.f32'))))

    for name,case in [('native','shadow-native'),('balanced','default'),('smooth','shadow-smooth'),
                      ('softest','shadow-softest'),('crisp','shadow-crisp'),('strength-zero','shadow-strength-zero'),
                      ('strength-half','shadow-strength-half'),('quality-zero','shadow-0-water-0'),
                      ('quality-medium','shadow-2-water-0'),('quality-high','shadow-3-water-0')]:
        job(name,case=case)
    job('repeat',frame_name='later')
    job('entity-only',terrain='clear',entity='diagonal')
    job('both-maps',entity='diagonal')
    job('no-occluder',terrain='clear')
    job('disabled-frame',shadow=shadow_data('disabled',enabled=0))
    for dimension in ('nether','end'):
        job(dimension,frame_name=dimension)
    outside = positions.copy()
    outside[:,:,0] = 40
    texture('outside',outside)
    job('outside-map',position='outside',terrain='blocked')
    outside[:,:,0] = 0
    outside[:,:,2] = 150
    texture('outside-depth',outside)
    job('outside-depth',position='outside-depth',terrain='blocked',shadow=shadow_data('long',splits=(256,)))

    # Independent coplanar depth map: the receiver plane must not shadow itself.
    slope_x,slope_y = .8,-.45
    sloped = positions.copy()
    sloped[:,:,2] = slope_x*px+slope_y*py
    texture('slope-position',sloped)
    texture('slope-normal',rgba(width,(-slope_x,-slope_y,1)))
    plane = rgba(map_size)
    plane_depth = .5-(slope_x*((mx/map_size-.5)*32)+slope_y*((my/map_size-.5)*32))/256
    plane[:,:,:3] = plane_depth[:,:,None]
    texture('coplanar',plane)
    for name,case in [('slope-balanced','default'),('slope-softest','shadow-softest')]:
        job(name,case=case,position='slope-position',normal='slope-normal',terrain='coplanar')

    def distance_positions(name,begin,end):
        p = rgba(width)
        p[:,:,2] = np.linspace(begin,end,width,dtype='<f4')[None,:]
        texture(name,p)

    distance_positions('fade-position',40,72)
    job('distance-fade',position='fade-position',terrain='blocked')
    distance_positions('handoff-position',24,36)
    job('cascade-handoff',position='handoff-position',shadow=shadow_data('two',splits=(32,64)),
        terrain='clear',cascade_maps={0:'blocked'})
    job('inactive-cascade',position='handoff-position',shadow=shadow_data('gap',splits=(32,64),active=[0,2]),
        terrain='clear',cascade_maps={0:'blocked'})
    config = output/'jobs.json'
    config.write_text(json.dumps({'jobs':jobs},indent=2)+'\n')
    subprocess.run([args.java,'--enable-native-access=ALL-UNNAMED','-cp',args.classpath,
                    'NativeRenderProbe',str(config)],check=True)
    rendered = {j['name']:np.fromfile(j['output'],dtype='<f4').reshape(height,width,4)[:,:,0] for j in jobs}
    assert all(np.isfinite(v).all() and v.min()>=0 and v.max()<=1.000001 for v in rendered.values())
    floor = 1-.92*.85
    balanced = rendered['balanced']
    assert abs(balanced.min()-floor)<1e-6 and abs(balanced.max()-1)<1e-6, 'Terrain cast shadow is absent or over-dark'
    assert np.array_equal(balanced,rendered['repeat']), 'Stationary shadows change with frame time'
    assert np.allclose(balanced,rendered['entity-only'],atol=1e-6), 'Entity map does not cast the expected shadow'
    assert np.allclose(balanced,rendered['both-maps'],atol=1e-6), 'Overlapping maps double-darken penumbra'
    for name in ('strength-zero','quality-zero','no-occluder','disabled-frame','nether','end','outside-map','outside-depth',
                 'slope-balanced','slope-softest'):
        assert np.allclose(rendered[name],1,atol=1e-6), 'Unexpected shadow in '+name
    assert np.all(rendered['strength-half']>=balanced-1e-6) and rendered['strength-half'].min()>floor+.2
    count = lambda image:int(np.count_nonzero((image>floor+.005)&(image<.995)))
    assert count(balanced)>count(rendered['native'])*1.5, 'Balanced filter does not soften the edge'
    assert count(rendered['softest'])>count(balanced), 'Softness control has no effect'
    assert np.max(np.abs(np.diff(balanced[64])))<np.max(np.abs(np.diff(rendered['native'][64]))), 'Filter does not reduce edge steps'
    fade = rendered['distance-fade'][64]
    assert abs(fade[0]-floor)<1e-6 and abs(fade[-1]-1)<1e-6
    assert np.all(np.diff(fade)>=-1e-6) and np.max(np.diff(fade))<.04, 'Shadow distance fade is discontinuous'
    handoff = rendered['cascade-handoff'][64]
    assert abs(handoff[0]-floor)<1e-6 and abs(handoff[-1]-1)<1e-6
    assert np.all(np.diff(handoff)>=-1e-6) and np.max(np.diff(handoff))<.03, 'Cascade seam is discontinuous'
    assert np.allclose(rendered['inactive-cascade'],rendered['cascade-handoff'],atol=1e-6), 'Inactive cascade is sampled'
    checks = dict(terrainOcclusion='PASS',entityOcclusion='PASS',overlapNoDoubleDarkening='PASS',
                  stableFilterPattern='PASS',softnessResponse='PASS',reducedEdgeSteps='PASS',
                  strengthControl='PASS',disabledAndDimensionBypass='PASS',mapAndDepthBounds='PASS',
                  slopedReceiverNoAcne='PASS',smoothDistanceFade='PASS',smoothCascadeHandoff='PASS',inactiveCascadeSkip='PASS')
    report = json.loads((output/'vulkan-render.json').read_text())
    report['checks'] = checks
    report['outputSha256'] = {j['name']:hashlib.sha256(Path(j['output']).read_bytes()).hexdigest() for j in jobs}
    report['testedSpirvSha256'] = {Path(j['fragment']).name:hashlib.sha256(Path(j['fragment']).read_bytes()).hexdigest() for j in jobs}
    report['metrics'] = dict(nativeTransitionPixels=count(rendered['native']),balancedTransitionPixels=count(balanced),
                             softestTransitionPixels=count(rendered['softest']),maximumDistanceFadeStep=float(np.diff(fade).max()),
                             maximumCascadeHandoffStep=float(np.diff(handoff).max()))
    report['limitations'] = ['Synthetic 64x64 shadow maps and 128x128 receivers; production helper executed through a diagnostic shader.',
                             'Does not test Minecraft shadow-map production, Sodium terrain draws, real scene quality, or hardware frame times.']
    (folder/'shadow-checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(draws=report['draws'],checks=checks,metrics=report['metrics']),indent=2))


if __name__=='__main__':
    main()
