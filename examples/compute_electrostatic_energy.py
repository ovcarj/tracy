"""Example: compute the 1D electrostatic energy profile E(z) for a molecule in a membrane.

Wires together:
  - ComputeMembranePotentialWorkChain.outputs.potential_profile  (SinglefileData, .xvg)
  - MoleculeChargeDistributionWorkChain.outputs.results[solvent_key].output_parameters

Replace POTENTIAL_PK and MOLECULE_PK with the AiiDA node PKs from your runs.
"""

from aiida import orm
from aiida.engine import run_get_node
from aiida.manage import load_profile

from tracy.workflows.electrostatic_energy import ElectrostaticEnergyWorkChain

load_profile()

# --- Replace these with your own PKs ---
POTENTIAL_PK = None  # ComputeMembranePotentialWorkChain pk
MOLECULE_PK = None   # MoleculeChargeDistributionWorkChain pk
SOLVENT_KEY = 'vacuum'  # 'vacuum' or 'water'
# ---------------------------------------

potential_wc = orm.load_node(POTENTIAL_PK)
molecule_wc = orm.load_node(MOLECULE_PK)

protocol = orm.Dict({
    'tracy': {
        'membrane_normal_axis': 'z',
        'charges_model': 'resp',
        'z_scan_nm': {
            'n_points': 200,
            # 'min': 1.0,  # optional: restrict to a sub-range (nm)
            # 'max': 7.0,
        },
    }
})

_, wc = run_get_node(
    ElectrostaticEnergyWorkChain,
    potential_profile=potential_wc.outputs.potential_profile,
    output_parameters=molecule_wc.outputs.results[SOLVENT_KEY].output_parameters,
    protocol=protocol,
)

report = wc.outputs.electrostatic_energy_report.get_dict()

print(f"Molecule:          {report['n_atoms']} atoms")
print(f"Dipole:            {report['dipole_magnitude_D']:.3f} D  "
      f"direction {[f'{x:.3f}' for x in report['dipole_direction']]}")
print()
print(f"+dipole scan:  z = {report['z_scan_nm_pos'][0]:.3f} – {report['z_scan_nm_pos'][-1]:.3f} nm")
print(f"  min E = {report['min_energy_eV_pos']:.4f} eV  "
      f"({report['min_energy_eV_pos'] * 96.485:.2f} kJ/mol)  at z = {report['min_z_nm_pos']:.3f} nm")
print(f"  max E = {report['max_energy_eV_pos']:.4f} eV  "
      f"({report['max_energy_eV_pos'] * 96.485:.2f} kJ/mol)  at z = {report['max_z_nm_pos']:.3f} nm")
print()
print(f"-dipole scan:  z = {report['z_scan_nm_neg'][0]:.3f} – {report['z_scan_nm_neg'][-1]:.3f} nm")
print(f"  min E = {report['min_energy_eV_neg']:.4f} eV  "
      f"({report['min_energy_eV_neg'] * 96.485:.2f} kJ/mol)  at z = {report['min_z_nm_neg']:.3f} nm")
print(f"  max E = {report['max_energy_eV_neg']:.4f} eV  "
      f"({report['max_energy_eV_neg'] * 96.485:.2f} kJ/mol)  at z = {report['max_z_nm_neg']:.3f} nm")
