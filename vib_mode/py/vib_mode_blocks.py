import pickle
import numpy as np
from numpy.linalg import eigh
from scipy.constants import physical_constants as pc
import common
from parser_g16 import g16_fchk_parser, flat_tril_to_sym
from parser_orca import orca_hess_parser

# Constants
default_SVD_threshold = 1e-2
default_Rot_threshold = 1e-3
# Calculates the conversion factor for Mass-Weighted frequency to cm-1:
# from sqrt(Hartree / (amu * Bohr^2)) to cm-1
# convert to atomic unit, then convert Hartree to cm-1
FC2CM = common.HARTREE2CM/np.sqrt(common.AMU2AU)
BOHR2ANGSTROM = common.BOHR2ANGSTROM

# dipole moment derivative conversion, 
# common.EBOHR2KMMOL = 31.223070185771018

class MolecularBlock:
    def __init__(self, indices, coords, masses):
        self.indices = np.array(indices)
        self.block_coords = coords[self.indices]
        self.block_masses = masses[self.indices].reshape(-1, 1)
        self.total_mass = np.sum(self.block_masses)
        self.com = np.sum(self.block_coords * self.block_masses, axis=0) / self.total_mass
        self.rel_coords = self.block_coords - self.com
        self.mw_factors = np.sqrt(np.repeat(self.block_masses.flatten(), 3)) # sqrt(m_i), used a lot
        self.SVD_threshold = default_SVD_threshold # vs 1e-8 need to decide
        self.Rot_threshold = default_Rot_threshold         

    def get_translation_vectors(self):
        n = len(self.indices)
        t_basis_unweighted = np.tile(np.eye(3), n) # row vec at the moment
        mw_t_basis = t_basis_unweighted * self.mw_factors
        mw_t_basis = mw_t_basis / np.linalg.norm(mw_t_basis, axis=1, keepdims=True) 
        return mw_t_basis.T # to column vecs

    def calculate_inertia_tensor(self):
        x, y, z = self.rel_coords.T
        m = self.block_masses.flatten()
        Ixx = np.sum(m * (y**2 + z**2))
        Iyy = np.sum(m * (x**2 + z**2))
        Izz = np.sum(m * (x**2 + y**2))
        Ixy, Ixz, Iyz = -np.sum(m*x*y), -np.sum(m*x*z), -np.sum(m*y*z)
        return np.array([[Ixx, Ixy, Ixz], [Ixy, Iyy, Iyz], [Ixz, Iyz, Izz]])

    def get_principal_rotation_vectors(self):
        inertia_tensor = self.calculate_inertia_tensor()
        w_rot, v_rot = eigh(inertia_tensor)
        n = len(self.indices)
        rot_basis = []
        for i in range(3):
            if w_rot[i] < self.Rot_threshold: # if eigenvalue is very large: linear molecule or point mass, skip it
                continue
            axis = v_rot[:, i]
            # for each atom rel_coord, the rot vec is orthogonal to the axis and rel_coord - cross product
            vec = np.array([np.cross(axis, r) for r in self.rel_coords]).flatten()
            rot_basis.append(vec) # row vec at the moment

        if not rot_basis: # single atom, return "empty" array with correct dimension 0*3N 
            # return np.empty((0, 3 * n))
            return np.empty((3 * n, 0)) # to 0 column vecs

        r_basis_unweighted = np.array(rot_basis)
        mw_r_basis = r_basis_unweighted * self.mw_factors
        mw_r_basis = mw_r_basis / np.linalg.norm(mw_r_basis, axis=1, keepdims=True)
        print(mw_r_basis.T.shape)
        return mw_r_basis.T # to column vecs

    def get_full_block_basis(self):
        t_basis = self.get_translation_vectors()
        r_basis = self.get_principal_rotation_vectors()
        combined = np.hstack([t_basis, r_basis])
        u, s, _ = np.linalg.svd(combined, full_matrices=False) # SVD for lazy orthogonalization
        print("Molecular Block Basis Orthonalization: Singular Value ", s)
        return u[:, s > self.SVD_threshold]
        # print(combined.shape)
        ## return combined ##

class HessianProjector:
    def __init__(self, full_hessian, blocks, masses, coords):
        self.hessian = full_hessian
        self.blocks = blocks
        self.N = full_hessian.shape[0]  # total dimension (3 * num_atoms)
        self.masses = masses
        self.coords = coords    
        self.SVD_threshold = default_SVD_threshold  

    def get_mass_weighted_hessian(self):
        """Applies 1/sqrt(mi*mj) to the Cartesian Hessian."""
        m_vec = np.repeat(np.sqrt(self.masses), 3)
        m_grid = np.outer(m_vec, m_vec)
        return self.hessian / m_grid
    
    def unweight_mode_vectors(self, v_mw, masses=None):
        if masses is None:
            masses = self.masses
        masses = masses
        mw_factors = np.sqrt(np.repeat(masses.flatten(), 3)) # sqrt(m_i), used a lot
        v_uw = v_mw / mw_factors.reshape(-1, 1)
        v_uw = v_uw / np.linalg.norm(v_uw, axis=1, keepdims=True)
        return v_uw
    
    def calculate_frequencies(self):
        raise NotImplementedError("This should be implemented in child classes.")
    
class PartialHessianProjector(HessianProjector):
    def __init__(self, full_hessian, blocks, masses, coords):
        super().__init__(full_hessian, blocks, masses, coords)

    def calculate_frequencies(self):
        """
        PHVA: 3N by 3N, block matrices
        """        
        mw_hessian = self.get_mass_weighted_hessian()        

        all_block_indices = np.hstack([b.indices for b in self.blocks]).flatten()
        total_dof = len(all_block_indices)*3
        w_total = []
        B_total = np.zeros((self.N, total_dof))
        
        current_col = 0
        for i, block in enumerate(self.blocks):
            row_indices = np.array([[3*idx, 3*idx+1, 3*idx+2] for idx in block.indices]).flatten()
            n_dof = row_indices.shape[0]
            mw_hessian_i = mw_hessian[np.ix_(row_indices, row_indices)]
            w_i, basis_i = eigh(mw_hessian_i)
            col_indices = range(current_col, current_col + n_dof)
            B_total[np.ix_(row_indices, col_indices)] = basis_i
            w_total.extend(w_i)
            current_col += n_dof
        freqs = np.sqrt(np.array(w_total, dtype=np.complex_))
        freqs = freqs * FC2CM
        return freqs, B_total

class NMHessianProjector(HessianProjector):
    def __init__(self, full_hessian, blocks, masses, coords):
        super().__init__(full_hessian, blocks, masses, coords)
        # block is not used

    def get_global_rigid_basis(self):
        """Constructs the 6 rigid modes for the ENTIRE molecule."""
        all_indices = np.arange(len(self.masses))
        super_block = MolecularBlock(all_indices, self.coords, self.masses)
        return super_block.get_full_block_basis() # (6, 3N)

    def assemble_global_basis(self):
        B_raw = np.eye(self.N)     
        B_super = self.get_global_rigid_basis()
        B_clean = B_raw - B_super @ (B_super.T @ B_raw)        
        u, s, _ = np.linalg.svd(B_clean, full_matrices=False) # lazy orthogonalization
        B_final = u[:, s > self.SVD_threshold]
        return B_final
 
    def calculate_frequencies(self):
        mw_hessian = self.get_mass_weighted_hessian()
        B = self.assemble_global_basis()
        H_red = B.T @ mw_hessian @ B
        w_red, v_red = eigh(H_red)
        ####
        ## w_red = H_red.diagonal()
        ## v_red = np.eye(H_red.shape[0])
        ####
        # freq may be imaginary! sqrt with "complex"
        freqs = np.sqrt(w_red.astype(np.complex_))
        # freqs = freqs.real - freqs.imag - prettify when printing
        freqs = freqs * FC2CM 
        return freqs, B@v_red # Back-project to Cartesian space

class MobileBlockHessianProjector(NMHessianProjector):
    def __init__(self, full_hessian, blocks, masses, coords):
        super().__init__(full_hessian, blocks, masses, coords)

    def get_ungrouped_indices(self):
        """Identifies atoms not assigned to any block."""
        set_atoms = set(range(len(self.masses)))
        for block in self.blocks:
            set_atoms.difference_update(block.indices)
        return [[i] for i in set_atoms]
    
    def assemble_global_basis(self):
        # MBH version: take translation + rotation basis for each block
        all_blocks = self.blocks
        ungrouped_blocks = self.get_ungrouped_indices()
        if ungrouped_blocks:
            print("ungrouped atom detected in MBH: automatically treat each atom as single block.")
            for group_i in ungrouped_blocks:
                block = MolecularBlock(indices=group_i, coords=self.coords, masses=self.masses)            
                all_blocks.append(block)

        all_block_bases = [b.get_full_block_basis() for b in all_blocks]
        total_dof = sum(basis.shape[1] for basis in all_block_bases)
        B_raw = np.zeros((self.N, total_dof))
        print(B_raw.shape)
        current_col = 0
        for i, block in enumerate(self.blocks):
            basis_i = all_block_bases[i] 
            n_dof = basis_i.shape[1]
            row_indices = np.array([[3*idx, 3*idx+1, 3*idx+2] for idx in block.indices]).flatten()
            col_indices = range(current_col, current_col + n_dof)
            B_raw[np.ix_(row_indices, col_indices)] = basis_i
            current_col += n_dof

        B_super = self.get_global_rigid_basis()
        B_clean = B_raw - B_super @ (B_super.T @ B_raw)        
        u, s, _ = np.linalg.svd(B_clean, full_matrices=False) # lazy orthogonalization
        print("MBH Basis Orthonalization: Singular Value ", s)
        B_final = u[:, s > self.SVD_threshold]
        return B_final
        ## return B_raw ##


class VibMode:
    def __init__(self, groups=None, source=None, is_1_based=True):
        if is_1_based and groups is not None:
            self.groups = shift_grouping(groups)
        else:
            self.groups = groups

        # molecule data: should be initialized
        self.atom_type = None
        self.coords = None
        self.masses = None
        self.hessian = None
        self.dipole_derivs = None 

        # other internal structures
        self.blocks = None
        self.projector = None

        self.freqs = None
        self.modes = None
        self.atom_info = None        
        self.mode_info = None

        if source is not None:
            self.auto_initializer(source)
            if groups is not None:
                self.update_blocks()
        return
           
    def auto_initializer(self, source):
        if source.endswith(".fchk"):
            self.update_from_fchk(source)
        elif source.endswith(".hess"):
            self.update_from_orca(source)
        else:
            print("MBH: \"%s\" file type not supported."%source)
        return

    def update_from_fchk(self, g16_fchk_name):
        g16_data = g16_fchk_parser(g16_fchk_name)
        self.atom_type = g16_data['Atomic numbers']        
        self.coords = g16_data['Current cartesian coordinates'].reshape(-1, 3) * BOHR2ANGSTROM
        self.masses = g16_data['Real atomic weights']
        hessian = g16_data['Cartesian Force Constants']
        self.hessian = flat_tril_to_sym(hessian)
        self.dipole_derivs = g16_data['Dipole Derivatives'].reshape(-1, 3)
        if self.groups is not None:
            self.update_blocks()
        return
    
    def update_from_orca(self, orca_hess_name):
        orca_data = orca_hess_parser(orca_hess_name)
        self.atom_type = orca_data['atoms'][:,0]
        self.coords = orca_data['atoms'][:,2:5] * BOHR2ANGSTROM
        self.masses = orca_data['atoms'][:,1]
        hessian = orca_data['hessian']
        self.hessian = (hessian + hessian.T) / 2 # Must be symmetric
        self.dipole_derivs = orca_data['dipole_derivatives']
        if self.groups is not None:
            self.update_blocks()
        return    

    def update_mass(self, masses):
        self.masses = masses
        if self.groups is not None:
            self.update_blocks()
        return

    def update_blocks(self, groups=None):
        if groups is not None:
            self.groups = groups
        block_lst = []
        for group_i in self.groups:
            block = MolecularBlock(indices=group_i, coords=self.coords, masses=self.masses)
            block_lst.append(block)
        self.blocks = block_lst
        return

    def calculate_NM(self):
        self.projector = NMHessianProjector(self.hessian, self.blocks, self.masses, self.coords)
        self.freqs, self.modes = self.projector.calculate_frequencies()        
        self.atom_info = np.vstack((self.atom_type, self.coords.T)).T
        self.mode_info = calculate_mode_info(self.freqs, self.modes, self.masses, self.dipole_derivs)
        return

    def calculate_PHVA(self):
        self.projector = PartialHessianProjector(self.hessian, self.blocks, self.masses, self.coords)
        self.freqs, self.modes = self.projector.calculate_frequencies()        
        self.atom_info = np.vstack((self.atom_type, self.coords.T)).T
        self.mode_info = calculate_mode_info(self.freqs, self.modes, self.masses, self.dipole_derivs)
        return
    
    def calculate_MBH(self):
        self.projector = MobileBlockHessianProjector(self.hessian, self.blocks, self.masses, self.coords)
        self.freqs, self.modes = self.projector.calculate_frequencies()        
        self.atom_info = np.vstack((self.atom_type, self.coords.T)).T
        self.mode_info = calculate_mode_info(self.freqs, self.modes, self.masses, self.dipole_derivs)
        return    
    
    def write_vibAnimation(self, filename): 
        write_vibAnimation(filename, self.atom_info, self.mode_info)
        return
    
    def dump_pickle(self, prefix="."):
        with open(prefix+'/atom.pickle', 'wb') as f:
            pickle.dump(self.atom_info, f)
        with open(prefix+'/mode_info.pickle', 'wb') as f:
            pickle.dump(self.mode_info, f)
        return
    
    def dump_all(self):        
        self.write_vibAnimation("./animate.log")
        self.dump_pickle()
        return
   
    def block_participation_ratio(self):
        # For each mode, calculate the sum of squared displacements per block
        # This helps identify if a mode is a "Water stretch" or a "CO wag"
        msq = self.modes**2
        participation = []
        for block in self.blocks:
            row_indices = np.array([[3*idx, 3*idx+1, 3*idx+2] for idx in block.indices]).flatten()
            participation.append(msq[row_indices].sum(axis=0))
        return np.array(participation).T


def real_freq(freq):
    return freq.real - freq.imag # - prettify when printing        
    
def calculate_mode_info(freqs, v_mw, masses, dipole_derivs=None):
    """
    freqs: MBH frequencies (cm-1)
    v_mw: Eigenvectors from H_red diagonalization and projected back to Btotal
    masses: N atomic masses (AMU)
    dipole_derivs: Optional (3, 3N) matrix from other software
    """
    real_freqs = freqs.real - freqs.imag # - prettify when printing     
    m_vec = np.repeat(masses, 3)    
    v_uw = v_mw / np.sqrt(m_vec).reshape(-1, 1)
    rmass = 1/(v_uw**2).sum(axis=0)    
    v_uw_normalized = v_uw / np.linalg.norm(v_uw, axis=0, keepdims=True)    
    inte = real_freqs * 0.0
    if dipole_derivs is not None:
        tdip_mode = v_uw.T@dipole_derivs
        inte = (tdip_mode**2).sum(axis=1)*common.EBOHR2KMMOL**2 # 974.8801118255833

    mode_info = list(zip(range(1, len(freqs)+1), real_freqs, rmass, v_uw_normalized.T, inte))
    return mode_info
    
def write_vibAnimation(filename, atom, mode_info):
    """
    atom: np.array [AtomicNumber, X, Y, Z]
    mode_list: list of [mode_index, freq, rmass, uw_norm_vec, intensity(optional)]    
    """

    # Text Preparation
    file_title    = "Gaussian, Inc.  All Rights Reserved.\n"
    file_title   += "  Entering Link 1 = l1.exe \n"

    blk_dilemeter = " ---------------------------------------------------------------------\n"
    orient_title  = " Center     Atomic      Atomic             Coordinates (Angstroms)\n" 
    orient_title += " Number     Number       Type             X          Y          Z\n"

    input_title   = "                           Input orientation:\n"
    input_title  += blk_dilemeter + orient_title + blk_dilemeter
    std_title     = "                        Standard orientation:\n"
    std_title    += blk_dilemeter + orient_title + blk_dilemeter

    freq_prefix   = ""
    freq_prefix  += " Harmonic frequencies (cm**-1), IR intensities (KM/Mole), Raman scattering \n"
    freq_prefix  += " activities (A**4/AMU), depolarization ratios for plane and unpolarized \n"
    freq_prefix  += " incident light, reduced masses (AMU), force constants (mDyne/A),\n"
    freq_prefix  += " and normal coordinates:\n\n"

    freq_suffix  = ""
    freq_suffix += "------------------- \n"
    freq_suffix += "- Thermochemistry - \n"
    freq_suffix += "------------------- \n"
    freq_suffix += "\n"
    freq_suffix += "Normal termination of Gaussian 09 \n"

    # INDEX AN 0 coord
    NAtom = atom.shape[0]
    atomIndex = np.arange(NAtom).reshape((-1,1)) + 1
    atomNum = atom[:,0].reshape((-1,1))
    geom = np.hstack([atomIndex, atomNum, np.zeros((NAtom,1)), atom[:,1:]])
    geom_str = ''
    for row in geom:
        line = '%6d%10d%12d%14.2f%14.2f%14.2f'%tuple(row.tolist()) + '\n'
        geom_str += line

    with open(filename, 'w') as f:
        f.write(file_title)
        f.write(input_title)
        f.write(geom_str)
        f.write(blk_dilemeter)
        f.write(std_title)
        f.write(geom_str)
        f.write(blk_dilemeter)
        f.write(freq_prefix)

        def format_gaussian_line(label, values):
            """Formats a label and 1-3 values into the fixed Gaussian width."""
            line = " %s %11.4f"%(label, values[0])
            if len(values) > 1:
                line += "%23.4f"%values[1]
            if len(values) > 2:
                line += "%23.4f"%values[2]
            line += "\n"
            return line

        mode_info_group = [mode_info[group_init:group_init+3] for group_init in range(0,len(mode_info),3)]
        for blk_mode_info in mode_info_group:
            mode_index = tuple(info[0] for info in blk_mode_info)
            freq = tuple(info[1] for info in blk_mode_info)
            rmass = tuple(info[2] for info in blk_mode_info)
            norm_vec = np.hstack([info[3].reshape(-1,3) for info in blk_mode_info])
            coord = np.hstack([atomIndex,atomNum,norm_vec])
            if len(blk_mode_info[0]) > 4:
                intensity = tuple(info[4] for info in blk_mode_info)
            else:
                intensity = (0,0,0)
            coord_title = "  Atom  AN"
            coord_item = "      X      Y      Z"
            coord_title += coord_item
            if len(freq) > 1:
                coord_title += "  " + coord_item
            if len(freq) > 2:
                coord_title += "  " + coord_item
            coord_title += "\n"

            f.write(format_gaussian_line("Frequencies --", mode_index))
            f.write(format_gaussian_line("Red. masses --", rmass))
            f.write(format_gaussian_line("Frc consts  --", intensity))            
            f.write(format_gaussian_line("IR Inten    --", freq))
            f.write(coord_title)
            coord_str = ''
            for row in coord:
                line  = "% 6d% 4d"%(row[0], row[1])
                for i, row_i in enumerate(row[2:]):
                    if i%3 == 0:
                        line += "  "
                    line += "% 7.2f"%row_i
                coord_str += line + '\n'
            f.write(coord_str)
            f.write("\n")
        f.write(freq_suffix)
        
def shift_grouping(grouping, offset=-1):
    """
    Recursively shifts all integers in a nested list structure.
    Default offset is -1 (converts 1-based to 0-based).
    """
    shifted = []
    for item in grouping:
        if isinstance(item, list):
            # If it's a list, go deeper
            shifted.append(shift_grouping(item, offset))
        else:
            # If it's an integer, apply the shift
            shifted.append(item + offset)
    return shifted
