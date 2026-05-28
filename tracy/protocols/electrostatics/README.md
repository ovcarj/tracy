# Electrostatics protocol directory

This directory will hold protocol files for the electrostatic potential
extraction stage (Milestone 3).

Each protocol file will describe:

- Trajectory time window and stride.
- Slice count along the membrane normal.
- Centering policy (e.g. centre on phosphorus atoms).
- Reference convention (e.g. bulk water = 0 V).
- Tool and command used (e.g. `gmx potential`).

Do not add protocol files here until `ComputeMembranePotentialWorkChain`
is implemented.
