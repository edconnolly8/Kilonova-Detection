# CLAUDE.md

## Project Overview

**Kilonova-Detection** is a simulation framework for kilonova detection in a synthetic local Universe (radius ≤ 300 Mpc). It models realistic galaxy populations, injects transient events (supernovae and kilonovae), simulates LSST-like survey observations, and performs detection efficiency analysis.

This is a scientific research project implemented as two sequential Jupyter notebooks.

---

## Workflow

Run the notebooks **in order**:

1. **`01_fake_universe Ed (1).ipynb`** — Builds a synthetic galaxy catalog (`galaxy_catalog.csv`)
2. **`02_kilonova_injectioned (1).ipynb`** — Injects transient events and simulates survey observations

```bash
jupyter notebook "01_fake_universe Ed (1).ipynb"
jupyter notebook "02_kilonova_injectioned (1).ipynb"
```

---

## Dependencies

No `requirements.txt` exists yet. The project relies on standard scientific Python packages:

- `numpy`
- `pandas`
- `matplotlib`
- `scipy`
- `jupyter`

Install with:

```bash
pip install numpy pandas matplotlib scipy jupyter
```

---

## External Data Files Required

Notebook 2 requires two observational light curve files not included in the repository:

| File | Description |
|------|-------------|
| `~/Downloads/sn1993j_rband_shifted.csv` | SN 1993J (Type IIb supernova) r-band light curve |
| `~/Documents/at2017gfo_rband.csv` | AT2017gfo (kilonova) r-band observations |

Update the file paths in Notebook 2 if your data lives elsewhere.

---

## Key Parameters

### Synthetic Universe (Notebook 1)

| Parameter | Value |
|-----------|-------|
| Universe radius | 300 Mpc |
| Number of galaxies | 50,000 |
| Stellar mass range | 10^9.5 – 10^12 M☉ |
| Quiescent fraction | ~40% (Baldry et al. 2006) |
| Random seed | 42 (reproducible) |

### Event Rates (Notebook 2)

| Parameter | Value |
|-----------|-------|
| Supernova rate | 1×10^-6 per (M☉/yr) per year |
| Kilonova rate | 1×10^-18 per M☉ per year |
| Survey duration | 500,000 years |
| Assumed absolute magnitude | M = −16 |

### Survey Cadence

- Observation epochs: t = 0, 1, 2, 3 days
- Photometric uncertainty: σ = 0.1 mag (m ≤ 20), σ = 0.2 mag (m ≥ 21), linear interpolation in between
- Injected transient distance range: 50–600 Mpc

---

## Outputs

| Output | Source Notebook | Description |
|--------|-----------------|-------------|
| `galaxy_catalog.csv` | Notebook 1 | Synthetic galaxy population |
| Various matplotlib plots | Both notebooks | Distributions, light curves, detection plots |

---

## Repository Structure

```
Kilonova-Detection/
├── CLAUDE.md
├── README.md
├── 01_fake_universe Ed (1).ipynb   # Step 1: Galaxy population synthesis
└── 02_kilonova_injectioned (1).ipynb # Step 2: Transient injection & survey sim
```

---

## Scientific Context

- **AT2017gfo** — Real kilonova event (GW170817 counterpart) used as a light curve template
- **SN 1993J** — Type IIb supernova used as a comparison transient class
- **Schechter functions** — Standard parametric forms for galaxy mass and luminosity distributions
- **LSST** — The survey design is motivated by LSST/Rubin Observatory cadence

---

## Development Notes

- No CI/CD is configured.
- There are no unit tests; validation is done visually through notebook plots and comparison with known observational data.
- Fixed random seeds (`np.random.seed(42)`) ensure reproducible outputs across runs.
- When modifying event rates or galaxy parameters, re-run Notebook 1 first before Notebook 2.
