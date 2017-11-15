"""Functions useful for processing spectral data."""

import numpy as np
from darkhistory import utilities as utils
import matplotlib.pyplot as plt
import warnings

from scipy import integrate


def get_bin_bound(eng):
    """Returns the bin boundary of an abscissa.
    
    The bin boundaries are computed by taking the midpoint of the **log** of the abscissa. The first and last entries are computed by taking all of the bins to be symmetric with respect to the bin center. 

    Parameters
    ----------
    eng : ndarray
        Abscissa from which the bin boundary is obtained.

    Returns
    -------
    ndarray
        The bin boundaries. 
    """
    if eng.size <= 1:
        raise TypeError("There needs to be more than 1 bin to get a bin width.")


    log_bin_width_low = np.log(eng[1]) - np.log(eng[0])
    log_bin_width_upp = np.log(eng[-1]) - np.log(eng[-2])

    bin_boundary = np.sqrt(eng[:-1] * eng[1:])

    low_lim = np.exp(np.log(eng[0]) - log_bin_width_low / 2)
    upp_lim = np.exp(np.log(eng[-1]) + log_bin_width_upp / 2)
    bin_boundary = np.insert(bin_boundary, 0, low_lim)
    bin_boundary = np.append(bin_boundary, upp_lim)

    return bin_boundary

def get_log_bin_width(eng):
    """Return the log bin width of the abscissa.

    Returns
    -------
    ndarray

    """
    bin_boundary = get_bin_bound(eng)
    return np.diff(np.log(bin_boundary))

def rebin_N_arr(N_arr, in_eng, out_eng):
    """Rebins an array of particle number with fixed energy.
    
    Returns a `Spectrum` object. The rebinning conserves both total number and total energy.

    Parameters
    ----------
    N_arr : ndarray
        An array of number of particles in each bin. 
    in_eng : ndarray
        An array of the energy abscissa for each bin. The total energy in each bin `i` should be `N_arr[i]*in_eng[i]`.
    out_eng : ndarray
        The new abscissa to bin into.

    Returns
    -------
    Spectrum
        The output `Spectrum` with appropriate dN/dE, with abscissa out_eng.

    Raises
    ------
    OverflowError
        The maximum energy in `out_eng` cannot be smaller than any bin in `self.eng`.

    Note
    ----
    The total number and total energy is conserved by assigning the number of particles N in a bin of energy eng to two adjacent bins in new_eng, with energies eng_low and eng_upp such that eng_low < eng < eng_upp. Then dN_low_dE_low = (eng_upp - eng)/(eng_upp - eng_low)*(N/(E * dlogE_low)), and dN_upp_dE_upp = (eng - eng_low)/(eng_upp - eng_low)*(N/(E*dlogE_upp)).

    If a bin in `in_eng` is below the lowest bin in `out_eng`, then the total number and energy not assigned to the lowest bin are assigned to the underflow. Particles will only be assigned to the lowest bin if there is some overlap between the bin index with respect to `out_eng` bin centers is larger than -1.0.

    If a bin in `in_eng` is above the highest bin in `out_eng`, then an `OverflowError` is thrown. 

    See Also
    --------
    spectrum.Spectrum.rebin
    """

    from darkhistory.spec.spectrum import Spectrum
    # This avoids circular dependencies.

    if N_arr.size != in_eng.size:
        raise TypeError("The array for number of particles has a different length from the abscissa.")

    if not np.all(np.diff(out_eng) > 0):
        raise TypeError("new abscissa must be ordered in increasing energy.")
    if out_eng[-1] < in_eng[-1]:
        raise OverflowError("the new abscissa lies below the old one: this function cannot handle overflow (yet?).")
    # Get the bin indices that the current abscissa (self.eng) corresponds to in the new abscissa (new_eng). Can be any number between 0 and self.length-1. Bin indices are wrt the bin centers.

    # Add an additional bin at the lower end of out_eng so that underflow can be treated easily.

    first_bin_eng = np.exp(np.log(out_eng[0]) - (np.log(out_eng[1]) - np.log(out_eng[0])))
    new_eng = np.insert(out_eng, 0, first_bin_eng)

    # Find the relative bin indices for self.eng wrt new_eng. The first bin in new_eng has bin index -1. 
    bin_ind = np.interp(in_eng, new_eng, 
        np.arange(new_eng.size)-1, left = -2, right = new_eng.size)

    # Locate where bin_ind is below 0, above self.length-1 and in between.
    ind_low = np.where(bin_ind < 0)
    ind_high = np.where(bin_ind == new_eng.size)
    ind_reg = np.where( (bin_ind >= 0) & (bin_ind <= new_eng.size - 1) )

    if ind_high[0].size > 0: 
        raise OverflowError("the new abscissa lies below the old one: this function cannot handle overflow (yet?).")

    # Get the total N and toteng in each bin
    toteng_arr = N_arr*in_eng

    N_arr_low = N_arr[ind_low]
    N_arr_high = N_arr[ind_high]
    N_arr_reg = N_arr[ind_reg]

    toteng_arr_low = toteng_arr[ind_low]

    # Bin width of the new array. Use only the log bin width, so that dN/dE = N/(E d log E)
    new_E_dlogE = new_eng * np.diff(np.log(get_bin_bound(new_eng)))

    # Regular bins first, done in a completely vectorized fashion. 

    # reg_bin_low is the array of the lower bins to be allocated the particles in N_arr_reg, similarly reg_bin_upp. This should also take care of the fact that bin_ind is an integer.
    reg_bin_low = np.floor(bin_ind[ind_reg]).astype(int)
    reg_bin_upp = reg_bin_low + 1

    # Takes care of the case where in_eng[-1] = out_eng[-1]
    reg_bin_low[reg_bin_low == new_eng.size-2] = new_eng.size - 3
    reg_bin_upp[reg_bin_upp == new_eng.size-1] = new_eng.size - 2

    reg_N_low = (reg_bin_upp - bin_ind[ind_reg]) * N_arr_reg
    reg_N_upp = (bin_ind[ind_reg] - reg_bin_low) * N_arr_reg

    reg_dNdE_low = ((reg_bin_upp - bin_ind[ind_reg]) * N_arr_reg
                   /new_E_dlogE[reg_bin_low+1])
    reg_dNdE_upp = ((bin_ind[ind_reg] - reg_bin_low) * N_arr_reg
                   /new_E_dlogE[reg_bin_upp+1])

    # Low bins. 
    low_bin_low = np.floor(bin_ind[ind_low]).astype(int)
                  
    N_above_underflow = np.sum((bin_ind[ind_low] - low_bin_low) 
        * N_arr_low)
    eng_above_underflow = N_above_underflow * new_eng[1]

    N_underflow = np.sum(N_arr_low) - N_above_underflow
    eng_underflow = np.sum(toteng_arr_low) - eng_above_underflow
    low_dNdE = N_above_underflow/new_E_dlogE[1]

    new_dNdE = np.zeros(new_eng.size)
    new_dNdE[1] += low_dNdE
    # reg_dNdE_low = -1 refers to new_eng[0]  
    for i,ind in zip(np.arange(reg_bin_low.size), reg_bin_low):
        new_dNdE[ind+1] += reg_dNdE_low[i]
    for i,ind in zip(np.arange(reg_bin_upp.size), reg_bin_upp):
        new_dNdE[ind+1] += reg_dNdE_upp[i]

    # Generate the new Spectrum.

    out_spec = Spectrum(new_eng[1:], new_dNdE[1:])
    out_spec.underflow['N'] += N_underflow
    out_spec.underflow['eng'] += eng_underflow

    return out_spec


def discretize(func_dNdE, eng):
    """Discretizes a continuous function. 

    The function is integrated between the bin boundaries specified by `eng` to obtain the discretized spectrum, so that the final spectrum conserves number and energy between the bin **boundaries**. 

    Parameters
    ----------
    func_dNdE : function
        A single variable function that takes in energy as an input, and then returns a dN/dE spectrum value. 
    eng : ndarray
        Both the bin boundaries to integrate between and the new abscissa after discretization (bin centers). 

    Returns
    -------
    Spectrum
        The discretized spectrum. rs is set to -1, and must be set manually. 

    """
    def func_EdNdE(eng):
        return func_dNdE(eng)*eng

    # Generate a list of particle number N and mean energy eng_mean, so that N*eng_mean = total energy in each bin. eng_mean != eng. 
    N = np.zeros(eng.size)
    eng_mean = np.zeros(eng.size)
    
    for low, upp, i in zip(eng[:-1], eng[1:], 
        np.arange(eng.size-1)):
    # Perform an integral over the spectrum for each bin.
        N[i] = integrate.quad(func_dNdE, low, upp)[0]
    # Get the total energy stored in each bin. 
        if N[i] > 0:
            eng_mean[i] = integrate.quad(func_EdNdE, low, upp)[0]/N[i]
        else:
            eng_mean[i] = 0


    return rebin_N_arr(N, eng_mean, eng)

def evolve(spec, tflist, end_rs=None, save_steps=False):
    """Evolves a spectrum using a list of transfer functions. 
    
    Parameters
    ----------
    spec : Spectrum
        The initial spectrum to evolve. 
    tflist_in : TransferFuncList
        The list of transfer functions for the evolution. Must be of type TransFuncAtEnergy.
    end_rs : float, optional
        The final redshift to evolve to.
    save_steps : bool, optional
        Saves every intermediate spectrum if true.

    Returns
    -------
    Spectrum or Spectra
        The evolved final spectrum, with or without intermediate steps. 

    """
    from darkhistory.spec.spectra import Spectra

    if not np.all(spec.eng == tflist.in_eng):
        raise TypeError("input spectrum and transfer functions must have the same abscissa for now.")

    if tflist.tftype != 'rs':
            tflist.transpose()

    if end_rs is not None:
        # Calculates where to stop the transfer function multiplication.
        rs_ind = np.arange(tflist.rs.size)
        rs_last_ind = rs_ind[np.where(tflist.rs > end_rs)][-1]

    else:

        rs_last_ind = tflist.rs.size-1 

    if save_steps is True:

        out_specs = Spectra([spec])
        append_spec = out_specs.append

        for i in np.arange(rs_last_ind):
            append_spec(tflist[i].sum_specs(out_specs[-1]))
            out_specs[-1].rs = tflist.rs[i+1]

        return out_specs

    else:

        for i in np.arange(rs_last_ind):
            spec = tflist[i].sum_specs(spec)
            spec.rs = tflist.rs[i+1]

        return spec





