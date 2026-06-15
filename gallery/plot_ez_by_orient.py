"""
Generate ez_mofm_bodipyet_by_orient.png — 2×2 E(z) grid for mofm vs BODIPY-Et
vs two membrane systems (POPC symmetric and POPC/POPE:POPS asymmetric).

mofm chosen as the representative mitochondria-targeting molecule (fm omitted for clarity).

Rows: POPC symmetric (top), POPC/POPE:POPS asymmetric (bottom)
Cols: +dipole (left), −dipole (right)
Colour: mofm=blue, BODIPY-Et=green
Style:  solid=CPCM water, dashed=vacuum
Fill:   shaded band between vacuum and water curves per molecule
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from retrace.registry import Registry as RetraceRegistry
from retrace.storage import load_energy_profile
from pathlib import Path

RETRACE_DB = '/home/juraj/.retrace'
OUTDIR = Path(__file__).parent

EV_TO_KJMOL = 96.485

IK_MOFM     = 'SRBYDGSVPUAXHX-UHFFFAOYSA-N'
IK_BODIPYET = 'QFMOOGZDKYIKAP-UHFFFAOYSA-N'

MEM_POPC = 'POPC:2'
MEM_ASYM = 'POPC:1 POPE:3 POPS:1'

MOLECULES = [
    (IK_MOFM,     'mofm',      '#2b7be0'),
    (IK_BODIPYET, 'BODIPY-Et', '#2ca02c'),
]
MEMBRANES = [MEM_POPC, MEM_ASYM]
MEM_LABELS = {
    MEM_POPC: 'POPC (symmetric)',
    MEM_ASYM: 'POPC / POPE:POPS (asymmetric)',
}

reg = RetraceRegistry(RETRACE_DB)
data = {}
for rec in reg.list():
    ik  = rec.molecule.inchikey
    sol = rec.molecule.solvent_key
    mem = rec.membrane.composition_label
    if ik in {ik_ for ik_, _, _ in MOLECULES} and mem in MEMBRANES:
        arr = load_energy_profile(reg.record_dir(rec.id))
        data[(ik, sol, mem)] = arr

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'font.size': 9,
    'axes.linewidth': 0.8,
    'xtick.direction': 'in',
    'ytick.direction': 'in',
    'xtick.top': True,
    'ytick.right': True,
    'xtick.minor.visible': True,
    'ytick.minor.visible': True,
    'lines.linewidth': 1.6,
    'legend.frameon': False,
    'legend.fontsize': 8,
})

fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharey='row', constrained_layout=True)

for row, mem_label in enumerate(MEMBRANES):
    ax_pos = axes[row, 0]
    ax_neg = axes[row, 1]

    for ax, orient in [(ax_pos, '+'), (ax_neg, '−')]:
        ax.axhline(0, color='black', lw=0.7, zorder=1)
        ax.set_xlabel('z  (nm)', fontsize=9)
        ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
        ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))
        ax.text(0.97, 0.96, f'{orient} dipole',
                transform=ax.transAxes, ha='right', va='top',
                fontsize=8.5, style='italic', color='#555555')

    ax_pos.set_ylabel('E(z)  (kJ mol⁻¹)', fontsize=9)
    ax_pos.set_title(MEM_LABELS[mem_label], fontsize=9, fontweight='bold', pad=4)
    ax_neg.set_title(MEM_LABELS[mem_label], fontsize=9, fontweight='bold', pad=4)

    for ik, name, color in MOLECULES:
        arr_vac = data.get((ik, 'vacuum', mem_label))
        arr_wat = data.get((ik, 'water',  mem_label))
        if arr_vac is None or arr_wat is None:
            continue

        for ax, zk, ek in [
            (ax_pos, 'z_scan_nm_pos', 'energy_eV_pos'),
            (ax_neg, 'z_scan_nm_neg', 'energy_eV_neg'),
        ]:
            z_vac = arr_vac[zk]
            e_vac = arr_vac[ek] * EV_TO_KJMOL
            z_wat = arr_wat[zk]
            e_wat = arr_wat[ek] * EV_TO_KJMOL

            # Interpolate vacuum onto water z-grid for fill_between
            z_common = z_wat
            e_vac_interp = np.interp(z_common, z_vac, e_vac)

            ax.fill_between(z_common, e_vac_interp, e_wat,
                            color=color, alpha=0.18, lw=0, zorder=2)

            # Lines on top of fill
            label_wat = f'{name} (CPCM water)' if row == 0 else None
            label_vac = f'{name} (vacuum)'      if row == 0 else None
            ax.plot(z_wat, e_wat, color=color, ls='-',  lw=1.6, label=label_wat, zorder=3)
            ax.plot(z_vac, e_vac, color=color, ls='--', lw=1.4, label=label_vac, zorder=3)

axes[0, 0].legend(loc='upper left', fontsize=7.5,
                  handlelength=1.8, labelspacing=0.3, borderpad=0.5)

out = OUTDIR / 'ez_mofm_bodipyet_by_orient.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f'Saved {out}')
plt.close(fig)
