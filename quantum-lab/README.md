# Quantum Light Lab v0.1.0

A standalone, offline educational double-slit experiment. No Aether imports,
server, runtime dependencies, build step, cloud connection, or hardware are required.
Development-only browser test dependencies are listed in `package.json`.

## Open

Open [index.html](./index.html) directly in a current Safari, Firefox, Chrome,
or Edge browser. Keep the four application files (`index.html`, `styles.css`,
`model.js`, `app.js`) together when copying the app elsewhere. Classic scripts,
not ES modules or fetch requests, allow it to work from a `file://` URL.

Start the experiment, emit individual photons, or add 1,000 at a time. Vary
which-path information to remove interference, or change wavelength and slit
separation to change fringe spacing. Changing any physics setting clears the
run; changing the rate does not. Clear run preserves the physics settings.
Hiding the tab pauses the simulation, with no background catch-up. Reduced-motion
preferences lower the visual refresh rate; the app starts paused.

Use **Explore the chart data** for numerical alternatives to the visualizations.
Tables refresh once a second during a run; pause for a stable snapshot.
**Export CSV** saves all histogram counts, expected probabilities, and model
parameters. Runs otherwise live only in memory and disappear on reload.
The screen retains the latest 6,000 dots and the trace the latest 160 detections;
the histogram and total counts retain every detection in the current run.

## What this demonstrates

Photons produce localized detections. Many detections reveal wave-like
interference when the two paths remain indistinguishable. Light does not
literally switch from being a classical wave to being a classical particle.
The schematic lines are not photon trajectories; vertical dot positions are
decorative, not a second diffraction calculation.

The far-field, small-angle model is:

```text
I(x) proportional to sinc(pi*a*x/(lambda*L))^2
                    * [1 + V*cos(2*pi*d*x/(lambda*L))]
sinc(z) = sin(z)/z, with sinc(0) = 1
V = sqrt(1 - D^2)
```

Here `a = 0.04 mm` is slit width, `d = 0.10..0.60 mm` is slit separation,
`L = 1.5 m` is screen distance, `lambda = 380..750 nm` is wavelength, and
`D = 0..1` is ideal path distinguishability. There are 120 screen bins of
width 0.25 mm over -15..+15 mm. Intensities are integrated over each bin using
composite Simpson quadrature with 64 subintervals and normalized over that
finite screen, so probabilities are conditional on detection in that region.
Within-bin dot positions are still uniform approximations; they do not follow
the continuous intensity within a bin. CSV exports identify the integration
method as `bin_integration=simpson_64`; older exports used bin-center weights.
The model omits efficiencies, losses, detector noise, and detailed propagation.

The complementarity equality assumes balanced paths and pure marker states.
At `D = 1` there is no interference, but the diffraction envelope remains;
the model does not predict two narrow classical bands.

The page also displays the notebook's equilibrium equation:
`E = integral_Ω [div(W·ξ) - P(1-ξ)] · S_eco dΩ = 0`.
The notes describe `W` as wave/fluid intelligence, `P` as particle/foundation
rules, `ξ` as a state switch, and `S_eco` as an ecosystem stewardship factor.
The notebook does not give quantitative definitions, units, or an integration
domain. The **Dimensionless equilibrium sandbox** chooses the following
explicit specification so this particular mathematical model can be evaluated:

| Quantity | Chosen definition | Units |
| --- | --- | --- |
| Ω, u | One-dimensional interval `[0, 1]`, coordinate `u` | Dimensionless (1) |
| W(u) | Linear one-dimensional flux `w*u`, `0 <= w <= 2` | Dimensionless (1) |
| P(u) | Constant `p`, `0 <= p <= 2` | Dimensionless (1) |
| ξ(u) | Constant wave weight `ξ`, `0 <= ξ <= 1` | Dimensionless (1) |
| S_eco(u) | Constant weight `s`, `0 <= s <= 1` | Dimensionless (1) |
| E | Signed weighted integral residual, not energy | Dimensionless (1) |

These are exploratory assumptions, not physical measurements or a validated
quantum law. The coordinate `u` is abstract, not detector position.
Fields are time-independent; boundary fluxes are `W(0)=0` and
`W(1)=w`. With `ξ` constant, `div(W*ξ) = d(w*u*ξ)/du = w*ξ`.
Integrating over the unit interval gives the exact result
`E = s * [w*ξ - p*(1-ξ)]`. Defaults are `w=p=s=1`, `ξ=0.5`, giving `E=0`.
For `s>0` and `w+p>0`, the unique equilibrium weight is `ξ=p/(w+p)`.
If `s=0` or `w=p=0`, every `ξ` gives zero residual; the UI reports that
there is no unique equilibrium weight instead of claiming a meaningful balance.
The balanced-state label uses `abs(E) < 1e-10` numerical tolerance.

The sliders evaluate these fields independently of the photon experiment.
Following the user's clarified convention, `ξ=1` weights the wave term and
`ξ=0` the particle term; `ξ` is not identified with which-path distinguishability
`D`. No dynamics or stability is inferred from `E=0`. The sandbox does not
alter photon counts or CSV exports. Its settings persist only until reload;
clearing the photon run leaves them unchanged.

### Unified Lagrangian sketches

The page also presents tentative readings of two handwritten sketches as
reference only. They are not inputs to the photon model or the equilibrium
sandbox and do not affect CSV exports:

```text
L ≈ L_loop - 1/4 F_(mu nu) F^(mu nu) + psi_bar (i gamma^mu D_mu - m) psi
D_mu ≈ partial_mu - i e A_mu - i Gamma_hat_mu

L_unified ≈ sqrt(-g) [(R + alpha R^2 + gamma R_bounce)/(16 pi G)
                      - 1/2 g^(mu nu) nabla_mu phi nabla_nu phi - V(phi)
                      - [dark-energy matrix term]]
```

The first term and connection symbol in the first sketch, and the bounce
notation and final matrix contraction in the second, are uncertain readings.
`R_bounce` is a placeholder for the handwritten bounce contribution, not a
defined function. The final matrix term is described rather than transcribed.
The notes label the connection as a quantum-gravity spin connection and describe
the second sketch in terms of gravitational curvature, a bounce contribution,
scalar-field dynamics, and dark-energy balance. They do not specify sufficient
definitions, conventions, dynamics, parameters or initial and boundary
conditions for calculation. These sketches are not empirical evidence or proof
of a Big Bounce, quantum gravity, or the origin of the universe.

The **Quantum cohesion** display is an explicitly illustrative proxy,
`V^2 = 1 - D^2`, using the lab's ideal visibility `V` and which-path
distinguishability `D`. Thus `D = 40%` displays `84%`. This is not a validated
calculation of the notebook's equilibrium integral or a measured physical
cohesion value.

### Three different information quantities

- **Path-state entropy:** von Neumann entropy of the reduced two-path state,
  with eigenvalues `(1 + V)/2` and `(1 - V)/2`. It ranges from 0 to 1 bit and
  measures mixedness of that state, not the screen-position histogram.
- **Screen entropy:** Shannon entropy `H = -sum(p * log2(p))` of the discretized
  model distribution. It depends on screen extent and bin size.
  The dashed trace estimates it from up to 128 recent detections and is biased
  low at small sample sizes.
- **Surprisal:** `-log2(P(bin))` for an individual detection. A rare-bin marker
  highlights outcomes with surprisal at least 8 bits (`P(bin) <= 1/256`).
  This threshold is an arbitrary visual convention. A spike is not proof of
  collapse, a wave-to-particle transition, or a new physical effect.

Random numbers come from **Math.random**, not quantum hardware. This app
does not measure real quantum entropy and must not be used as a cryptographic
random source. It makes no requests to external services.

For physics background, see the open educational
[OpenStax treatment of the double-slit experiment](https://openstax.org/books/university-physics-volume-3/pages/3-2-mathematics-of-interference)
and [double-slit diffraction](https://openstax.org/books/university-physics-volume-3/pages/4-3-double-slit-diffraction).
For the general inequality `D^2 + V^2 <= 1`, see B.-G. Englert,
["Fringe Visibility and Which-Way Information: An Inequality,"
Physical Review Letters 77, 2154-2157 (1996)](https://doi.org/10.1103/PhysRevLett.77.2154).
This app chooses the ideal saturated case, not a universal equality.
These are optional reading links, not runtime dependencies.

## Mathematical verification and scientific review

The explicit sandbox permits a proof under its chosen assumptions:

1. In one dimension the divergence is a derivative. With constant `ξ`,
   `d(Wξ)/du = d(w*u*ξ)/du = wξ`.
2. The integrand `s[wξ - p(1-ξ)]` is constant over `[0,1]`.
   Multiplication by interval length 1 yields the exact implemented residual.
3. Rearrangement gives `E = s[(w+p)ξ-p]`. For positive `s` and `w+p`,
   dividing by their nonzero product proves `ξ=p/(w+p)`.
4. If either factor is zero, every `ξ` gives zero residual. A unique balance
   cannot be inferred. For example, zero stewardship suppresses all evidence
   of imbalance; it does not demonstrate a healthy physical system.

This proves only the reduction of the specified mathematical sandbox. It does
not prove the original notebook's unrestricted equation or a physical theory.
Spatially varying `ξ` would add the `W*dξ/du` product-rule term. Spatially
varying stewardship cannot be taken outside the integral. The current controls
do not represent either case. A vanishing integral generally does not require
pointwise balance; here the integrand is constant by construction.

### Photon model verification

For equal slits, let `A(x)` be the common single-slit amplitude and let
`delta = pi*d*x/(lambda*L)`. Summing the two path amplitudes gives
`|A exp(i delta) + A exp(-i delta)|^2 = 4 |A|^2 cos^2(delta)`.
Using `2 cos^2(delta) = 1 + cos(2 delta)`, this is proportional to the
implemented coherent intensity. The single-slit amplitude `A` is proportional
to `sinc(pi*a*x/(lambda*L))`. The constant factor cancels when the integrated
weights are normalized. For partial coherence, a visibility-weighted mixture
of coherent and incoherent intensities yields the same interference factor.
These derivations establish consistency with the stated ideal model, not
empirical validity or an exact description of every apparatus.

The checks in `reference.test.cjs` integrate independently constructed complex
amplitudes and coherent/incoherent mixtures using eight-point Gauss-Legendre
quadrature, rather than the implementation's Simpson rule. For wavelengths
380, 550 and 750 nm, separations 0.10, 0.25 and 0.60 mm, and
distinguishabilities 0, 0.2, 0.4, 0.8 and 1, the normalized distributions
must have total variation distance below `1e-9`. This checks those points,
not every possible slider setting or the true physical experiment.
Other tests check normalization, symmetry, seeded sampling, entropy and limits.
The equilibrium reference also integrates finite-difference fluxes over 1,000
cells and checks the integral to `1e-10`. These are independently formulated
checks in this codebase, not an external peer review.

The optical phase arguments are dimensionless: `a*x/(lambda*L)` and
`d*x/(lambda*L)` divide length squared by length squared. Fringe spacing
`lambda*L/d` has length units. The default predicts 3.30 mm. At the smallest
supported wavelength and largest separation it is 0.95 mm, only 3.8 screen bins
per fringe. Bin integration improves histogram probabilities but the 120-bin
display still cannot resolve all fine details; this is not a precision
propagation solver. The screen's maximum angle is
approximately 0.01 radians. The far-field approximation is assumed, not
validated against a full propagation calculation.

**Scientific status:** the optical component implements established idealized
theory; the notebook component is an explicitly chosen dimensionless toy model;
"Quantum cohesion" names the illustrative `V^2` proxy. No measured datasets,
instrument calibration, uncertainty budget, or empirical comparison have been
supplied. There is consequently no experimental validation of the notebook
equation, ecosystem factor, or any new cohesion observable. No result here
establishes collapse, thermodynamic equilibrium, stability, or a new quantum law.
Physical validation would require operational definitions of measurable fields,
preregistered falsifiable predictions distinct from standard theory, measured
data with uncertainties and controls, and independent replication.

### Big Bounce: evidence and process

Ashtekar, Pawlowski and Singh, [*Quantum Nature of the Big Bang: An Analytical
and Numerical Investigation*](https://doi.org/10.1103/PhysRevD.73.124038)
(2006), derive and numerically study a bounce in a **homogeneous, isotropic
loop quantum cosmology model with a massless scalar field**. That is a result
under specified theoretical assumptions, not a demonstration that our
universe underwent a bounce. See also their
[loop quantum cosmology review](https://doi.org/10.1088/0264-9381/28/21/213001).
This photon lab does not simulate cosmological evolution, test those papers'
equations, or establish that the handwritten Lagrangian reduces to either model.

To investigate the notebook hypothesis reproducibly: first supply an exact
action, definitions, units and conventions for every term; derive its field
equations and specify a cosmological ansatz and initial conditions; identify a
testable prediction and an independently reproducible numerical benchmark;
then compare it with suitable observations, uncertainties and competing
models. Independent scientific review and replication are needed. Neither
passing software tests nor producing a simulated bounce alone would establish
an observed bounce or prove a physical theory.

## Validate

Use Node.js 22 for local lab development. With nvm installed:

```bash
cd quantum-lab
nvm install
nvm use
cd ..
```

The lab's `.nvmrc` selects Node 22 without changing the main repository's
Node 24 CI requirement. New terminals use your configured nvm default; an
already-open terminal may need `nvm use 22`.

From the repository root:

```bash
node --test quantum-lab/model.test.cjs
node --check quantum-lab/app.js
```

The dependency-free tests cover normalization and symmetry across parameter
extremes, loss of interference, entropy endpoints, fringe spacing, sampling
boundaries, seeded convergence, bounded visual history, reset, invalid inputs,
and exported data shape.
They also check the dimensionless integral, residual signs, equilibrium
weights, zero-weight degeneracies, and invalid field inputs.

For repeatable browser checks, from this directory:

```bash
npm ci
npx playwright install chromium firefox webkit
npm run test:all
```

On Linux, installing browser system libraries may also require
`npx playwright install --with-deps chromium firefox webkit`.
The pinned development dependencies and lockfile are included in the release.
No browser-test package is loaded by the application.
The three projects exercise offline file loading, reset isolation, equilibrium
degeneracies, numerical tables, actual CSV downloads, start/pause/clear,
keyboard controls, 320-pixel layout, reduced motion, reload, explicit canvas
failure, JavaScript-disabled messaging, and automated axe accessibility rules.
The visibility test dispatches a synthetic hidden-tab event; it does not
substitute for a real background/suspension test on each device.
Automated accessibility tests do not certify WCAG compliance or replace
screen-reader testing with users.

For manual browser checks, open the file with the network offline, emit one
photon and a batch, start/pause, move which-path information to 100%, inspect
both chart tables, export a CSV, clear the run, and check a narrow viewport.
Use Tab, Enter/Space, and arrow keys to operate native buttons and sliders.
In the equilibrium sandbox, verify the default zero residual, move `ξ` to 0
and 1 to obtain -1 and +1, and set stewardship to zero to see the explicit
non-unique warning. These changes must not clear the photon run or change the
cohesion proxy.

## Local release

Version 0.1.0 is an exploratory educational release, not a scientific
certification. Extract the archive and open `quantum-lab/index.html`; no
installation is needed to use the app. Tests can be reproduced with the
commands above. Keep the included source, lockfile, tests, and documentation
when sharing reproducible results. Publishing the source to GitHub does not
deploy it to a website or a package registry.

### Release verification record

Local verification on macOS ARM64 using Node 22.23.5, Playwright 1.65.0,
and axe integration 4.14.0:

| Check | Result |
| --- | --- |
| Model, numerical-reference tests, and JS syntax | 17 tests passed; both application scripts passed syntax checks |
| Chromium browser tests | 12 passed |
| WebKit browser tests | 12 passed |
| Automated accessibility | No violations of the selected axe WCAG A/AA rules in the tested expanded page in either engine |
| Firefox | Blocked before application load: bundled Firefox reports "Could not find profile folder"; retry with a standard temporary directory also failed |
| Empirical validation of notebook equation | Not performed: no measured dataset, calibration, or operational physical field definitions supplied |
| Independent human scientific review | Not performed |
| Screen-reader users, real mobile devices, real tab suspension | Not tested; narrow layout, keyboard, reduced motion, and synthetic visibility tests are not substitutes |

Run the verified browser subset with
`npm run test:browser -- --project=chromium --project=webkit`.
The default browser command still includes Firefox, does not suppress failures,
and may fail at launch in this environment. A WebKit engine pass is not
certification for all Safari versions, and a Chromium engine pass is not a
test of every Chrome or Edge release. These limitations are intentionally
retained in the release instead of being presented as completed validation.

The archive includes `SHA256SUMS` for its source and documentation. From the
extracted `quantum-lab` directory, run `shasum -a 256 -c SHA256SUMS` (macOS)
or `sha256sum -c SHA256SUMS` (Linux). An adjacent checksum file verifies the
archive itself. Checksums detect changes; they are not a digital signature or
an independent endorsement.

Original code is covered by the included [MIT license](./LICENSE).
