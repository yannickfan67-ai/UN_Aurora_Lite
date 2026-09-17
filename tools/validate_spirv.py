#!/usr/bin/env python3
"""Validate release-compiled modules and the actual cross-stage/native buffer ABI."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import struct
import subprocess

def inspect(path):
    data = Path(path).read_bytes()
    words = struct.unpack('<' + 'I' * (len(data) // 4), data)
    assert words[0] == 0x07230203
    names, types, variables, decorations, members = {}, {}, {}, {}, {}
    cursor = 5
    while cursor < len(words):
        length, op = words[cursor] >> 16, words[cursor] & 0xffff
        assert length > 0
        args = words[cursor + 1:cursor + length]
        if op == 5:
            names[args[0]] = struct.pack('<' + 'I' * (len(args)-1), *args[1:]).split(b'\0')[0].decode()
        elif 19 <= op <= 39:
            types[args[0]] = (op, args[1:])
        elif op == 59:
            variables[args[1]] = (args[0], args[2])
        elif op == 71:
            decorations.setdefault(args[0], {})[args[1]] = args[2:]
        elif op == 72 and args[2] == 35:
            members.setdefault(args[0], {})[args[1]] = args[3]
        cursor += length
    def shape(type_id):
        op, args = types[type_id]
        if op == 32: return shape(args[1])
        if op == 21: return ('int' if args[1] else 'uint', args[0])
        if op == 22: return ('float', args[0])
        if op == 23: return ('vec', args[1], shape(args[0]))
        return (op, args)
    result = {'inputs': {}, 'outputs': {}, 'offsets': {names.get(t, str(t)): [m[i] for i in sorted(m)] for t, m in members.items()}}
    for variable, (type_id, storage) in variables.items():
        dec = decorations.get(variable, {})
        if storage not in (1, 3) or 30 not in dec: continue
        result['inputs' if storage == 1 else 'outputs'][names[variable]] = {
            'location': dec[30][0], 'type': shape(type_id), 'flat': 14 in dec}
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--spirv-val', default='spirv-val')
    args = parser.parse_args()
    report = json.loads((args.folder / 'native-compile.json').read_text())
    def validate(module):
        command = [args.spirv_val, '--target-env', 'vulkan1.2', module['spirv']]
        check = subprocess.run(command, capture_output=True, text=True)
        if check.returncode: raise RuntimeError(module['spirv'] + '\n' + check.stdout + check.stderr)
        return inspect(module['spirv'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        reflected = list(pool.map(validate, report['modules']))
    vertex = {m['case']: r for m, r in zip(report['modules'], reflected) if m['entry'] == 'shaders/terrain.vsh'}
    fullscreen = next(r for m, r in zip(report['modules'], reflected) if m['entry'] == 'fullscreen.vert')
    pairs = 0
    uint, flt = ('uint', 32), ('float', 32)
    attributes = {'a_Position': ('vec', 2, uint), 'a_Color': ('vec', 4, flt),
                  'a_TexCoord': ('vec', 2, uint), 'a_LightAndData': ('vec', 4, uint), 'a_SulkanMaterial': uint}
    globals_offsets = [0, 64, 128, 144, 152, 160, 168, 176, 180]
    frame_offsets = [0,64,128,192,256,320,384,400,416,432,448,464,480,496,512,528,544,560,576,640]
    for m, reflection in zip(report['modules'], reflected):
        if m['entry'] == 'shaders/terrain.vsh':
            for location, (name, kind) in enumerate(attributes.items()):
                assert reflection['inputs'][name]['type'] == kind, (m, name)
                assert reflection['inputs'][name]['location'] == location, (m, name)
            assert reflection['offsets']['PC'] == [0,12,16]
        if 'u_Globals' in reflection['offsets']: assert reflection['offsets']['u_Globals'] == globals_offsets
        if 'SulkanFrame' in reflection['offsets']: assert reflection['offsets']['SulkanFrame'] == frame_offsets
        if 'SulkanShadowData' in reflection['offsets']: assert reflection['offsets']['SulkanShadowData'] == [0,256,320,336]
        if m['entry'].endswith('.fsh'):
            previous = vertex[m['case']] if m['entry'] == 'shaders/terrain.fsh' else fullscreen
            for name, value in reflection['inputs'].items():
                assert previous['outputs'].get(name) == value, (m, name, previous['outputs'].get(name), value)
            pairs += 1
    summary = {'target': 'vulkan1.2', 'modules': len(reflected), 'spirvValidation': 'PASS',
               'stagePairs': pairs, 'stageInterfaces': 'PASS', 'sodiumVertexAbi': 'PASS',
               'globalsOffsets': 'PASS', 'frameOffsets': 'PASS', 'shadowOffsets': 'PASS', 'pushConstantOffsets': 'PASS',
               'vulkanDeviceCreated': False, 'inGameTested': False}
    (args.folder / 'spirv-validation.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary))

if __name__ == '__main__': main()
