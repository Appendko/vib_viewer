import sys
codepath = "/home/qrhuang/util_dvr/vib_mode_class"
sys.path.append(codepath)

import numpy as np
from vib_mode_blocks import VibMode
from vib_mode_blocks import real_freq, FC2CM
from vib_mode_blocks import g16_fchk_parser, flat_tril_to_sym
mass_update_fchk = None

g16_fchk = "../opt/OxH_ts.fchk"
grp = [[1],[2],[3],[4],[5],[6],[7]]

mass_update_fchk = "OxD_massupdate.fchk"

Vib = VibMode(grp, g16_fchk)
if mass_update_fchk:
    mass_update = g16_fchk_parser(mass_update_fchk)['Real atomic weights']
    Vib.update_mass(mass_update)
Vib.calculate_NM()
freq = real_freq(Vib.freqs)
print(f"Reduced PHVA Frequencies (cm^-1):\n{freq}")
Vib.dump_all()

