#!/usr/bin/env python3
"""Collect completed probe results; require current shaders to match the tested ZIP."""
import argparse
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--loader', type=Path, required=True)
    parser.add_argument('--client', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root/'sulkan.json').read_text())
    with zipfile.ZipFile(args.archive) as tested:
        for p in [root/'sulkan.json',root/'tools/shadow-probe.fsh', *sorted((root/'shaders').glob('*'))]:
            if p.is_file():
                assert p.read_bytes() == tested.read(p.relative_to(root).as_posix()), f'Untested changes: {p}'
    loader = json.loads((args.folder/'loader-probe.json').read_text())
    native = json.loads((args.folder/'native-compile.json').read_text())
    spirv = json.loads((args.folder/'spirv-validation.json').read_text())
    pixels = json.loads((args.folder/'render-checks.json').read_text())
    shadow_pixels = json.loads((args.folder/'shadow-checks.json').read_text())
    assert all(loader[k] == 'PASS' for k in ('packFilesRead','packGraphParse','shaderPackScanner'))
    assert all(m['status'] == m['minecraftRebind'] == 'PASS' for m in native['modules'])
    assert spirv['spirvValidation'] == spirv['stageInterfaces'] == 'PASS'
    assert all(v == 'PASS' for v in pixels['checks'].values())
    assert all(v == 'PASS' for v in shadow_pixels['checks'].values())
    assert native['moduleCount'] == spirv['modules']
    tested_modules = {Path(m['spirv']).name:Path(m['spirv']) for m in native['modules']}
    for record in (pixels,shadow_pixels):
        for name,expected in record['testedSpirvSha256'].items():
            assert digest(tested_modules[name]) == expected, f'Stale pixel results: {name}'
    # Pinned Sulkan 0.4.2 budget formula, not physical VRAM measurements.
    # Target sizes: 4 terrain cascades and 2 entity cascades, 5 bytes/texel + 560.
    shadow_sizes = {0: (), 1: (1536,1,1,1,768,1),
                    2: (2048,1536,1024,1,1536,768),
                    3: (3072,2048,1536,1024,3072,1024)}
    cases = copy.deepcopy(loader['cases'])
    for case in cases:
        quality = int(case['overrides'].get('SHADOW_QUALITY',manifest['options']['SHADOW_QUALITY']['default']))
        shadow = 0 if quality == 0 else 560+5*sum(s*s for s in shadow_sizes[quality])
        for allocation in case['allocations']:
            capture = allocation['width']*allocation['height']*20
            allocation.update(shadowBudgetBytes=shadow, sceneCaptureBytes=capture,
                              releaseBudgetAccountedBytes=allocation['graphTargetBytes']+shadow+capture)
            assert allocation['releaseBudgetAccountedBytes'] <= manifest['budgetMiB']*1024*1024
    summary = dict(date=str(date.today()), pack=manifest['name'], sulkanVersion='0.4.2', minecraftVersion='26.2',
                   loaderSha256=digest(args.loader), minecraftClientSha256=digest(args.client),
                   manifestSha256=digest(root/'sulkan.json'),
                   shaderSha256={p.relative_to(root).as_posix():digest(p) for p in sorted((root/'shaders').glob('*')) if p.is_file()},
                   scanner=loader['shaderPackScanner'], archiveRead=loader['packFilesRead'], manifestParse=loader['packGraphParse'],
                   optionCount=len(manifest['options']), legalOptionChoices=loader['optionChoiceCount'],
                   scenarioCount=len(loader['cases']), compiledModules=native['moduleCount'],
                   productionModules=native['productionModuleCount'], diagnosticModules=native['diagnosticModuleCount'],
                   productionEntrypoints=loader['productionEntrypoints'], diagnosticEntrypoints=loader['diagnosticEntrypoints'],
                   compiler=native['compiler'], target='Vulkan 1.2', nativeReflection='PASS', minecraftRebind='PASS',
                   spirvChecks=spirv, softwareVulkanChecks=pixels, shadowVulkanChecks=shadow_pixels,
                   totalVulkanDraws=pixels['draws']+shadow_pixels['draws'], memoryBudgetMiB=manifest['budgetMiB'],
                   vulkanDeviceCreated=True, softwareVulkanRenderingTested=True,
                   hardwareGpuRenderingTested=False, inGameTested=False, fpsMeasured=False,
                   notes=['Original release parser/compiler/reflection were used, without stubs.',
                          'Software Vulkan draws used synthetic post-process inputs and a diagnostic entrypoint calling the production shadow helper; no Minecraft world or Sodium terrain draw was run.',
                          'Static SPIR-V check metadata describes that check alone; the separate pixel probe creates a Vulkan device.',
                          'Budget estimates follow loader accounting, not measured total VRAM.'],
                   changes=['Native/balanced/smooth shadow sampling; deterministic 4/9-tap PCF using loader comparison helpers',
                            'Adjustable shadow softness and strength, applied to direct light without darkening ambient/torch light',
                            'Wider valid cascade overlap blend and smooth shadow distance fade',
                            'Shared sky glow now contributes to analytic water and wet-surface reflections',
                            'Shadow UBO ABI checked; synthetic terrain/entity maps, slope bias, bounds, overlap and cascade tests',
                            'No new graph textures or passes; additional shadow samples have unmeasured hardware cost'])
    records = {'summary.json':summary, 'scenarios.json':{'cases':loader['cases']},
               'modules.json':{'modules':[{k:v for k,v in m.items() if k!='spirv'} for m in native['modules']]},
               'memory-budget.json':{'description':'Release graph allocations plus Sulkan 0.4.2 shadow budget formula and conservative scene captures (20 bytes/pixel). Not measured VRAM.',
                                     'budgetMiB':manifest['budgetMiB'],'cases':cases},
               'render-checks.json':pixels, 'shadow-checks.json':shadow_pixels}
    for name, record in records.items():
        (root/'validation'/name).write_text(json.dumps(record,indent=2)+'\n')
    print(f"Collected {len(records)} records: {len(cases)} scenarios, {native['moduleCount']} modules, {pixels['draws']+shadow_pixels['draws']} Vulkan draws")


if __name__ == '__main__':
    main()
