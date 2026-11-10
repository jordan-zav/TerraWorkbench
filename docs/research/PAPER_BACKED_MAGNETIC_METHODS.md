# Paper-backed magnetic processing

TerraWorkbench owns all numerical methods below. ARCHIE provides the archaeological workflow, bilingual controls, recipe selection and file publication. These methods are optional; existing acquisition presets remain unchanged.

## Directional discrete wavelets

The grid tool and sequential filter WAVELET attenuate selected NS or EW detail coefficients. Level 1 is the finest. Direction uses grid axes. Approximation, diagonal details and the other directional detail remain unchanged. Users choose the basis, decomposition depth, first and last levels, and attenuation strength.

Fedi and Florio, Decorrugation and removal of directional trends of magnetic fields by the wavelet transform: application to archaeological areas. Geophysical Prospecting, 2003. https://doi.org/10.1046/j.1365-2478.2003.00373.x

Bianco et al., Magnetic and GPR Data Modelling via Multiscale Methods in San Pietro in Crapolla Abbey, Massa Lubrense (Naples). Archaeological Prospection, 2024. https://doi.org/10.1002/arp.1936

Our independent implementation uses selectable orthogonal wavelets. Bianco et al. used an interpolating mother wavelet; the numerical implementations differ. Detail scale metadata gives approximate dyadic spacing, not a sharp wavelength passband. Real structures sharing an orientation and scale can change.

The raster adapter publishes the filtered grid, removed component and parameter/source-hash manifest. Source finite support, geometry, units and CRS remain unchanged. Nearest filling, reflected padding and symmetric wavelet boundaries are recorded. PyWavelets is an optional shared dependency loaded only for this tool.

## Temporal notch

The per-sensor/profile notch uses a second-order IIR filter applied forward and backward. Frequency and Q are explicit; bandwidth of the single-pass filter is frequency divided by Q. The forward/backward response is squared. Timestamps and regular sampling are required. Irregular runs may be explicitly resampled within finite runs; nulls, resets and configured gaps remain split. Unsupported short runs become null and are counted.

Magnetotelluric Power Line Noise Removal Using Temporally Varying Sinusoidal Subtraction of the Grid Utility Frequency. Pure and Applied Geophysics, 2023. https://doi.org/10.1007/s00024-023-03323-w

This paper discusses notch filtering and its loss of neighbouring frequencies when utility frequency varies. Its main adaptive sinusoidal method is not implemented here. The reference supports geophysical narrow-band rejection, not acceptance of a particular survey setting. A 60 Hz centre must be justified by the measured spectrum.

## Existing lag and traverse controls

Manual lag and optional lag estimation already exist in TerraWorkbench. ARCHIE maps them through preprocessing. GPS(t + lag) belongs to the magnetic sample at t; unsupported endpoints remain null. The automatic estimator is independent and requires suitable opposite traverses.

Kolster et al., Simultaneous line shift and source parameter inversion applied to a scalar magnetic survey for small unexploded ordnance. Near Surface Geophysics, 2021. https://doi.org/10.1002/nsg.12178

Thresholded traverse mean/median correction already exists. Background limits select samples for estimating the offset; they do not clip the output signal. The archaeological choice of thresholds and recipe belongs to ARCHIE.

Linford, Linford and Payne, Geophysical Survey Methodology. Internet Archaeology, 2018. https://intarch.ac.uk/journal/issue47/7/app6.html

## Verification

Controlled tests cover selective 60 Hz rejection with a retained 1 Hz signal, constant-field preservation, invalid sampling/Nyquist, short runs, source immutability, missing-data gaps, NS/EW wavelet orientation, injected stripes, mask restoration, odd shapes, invalid levels, sequential recipe provenance and GUI configuration round-trip. Scientific and workflow regressions are run alongside them. These checks establish implementation behaviour; selecting survey-specific settings requires comparing real output maps and anomaly changes.
