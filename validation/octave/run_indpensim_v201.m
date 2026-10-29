## run_indpensim_v201.m - run IndPenSim V2.01 under GNU Octave and save inputs and outputs batch by batch.
##
## Usage (from the repository root):
##   octave-cli --no-gui validation/octave/run_indpensim_v201.m <IndPenSim_V2.01 folder> <output folder> [case ids]
##
## The V2.01 sources are copied to <output folder>/src, the Octave compatibility edits listed in PATCHES are
## applied to that copy, and each case in CASES is run. The model, the controller and the main loop are V2.01's
## own code (indpensim.m, indpensim_ode.m, fctrl_indpensim.m, Parameter_list.m, ...). Only the random setup block
## of indpensim_run.m is repeated below, with an explicit seed (Random_seed_ref) where V2.01 draws
## ceil(rand*1000), so that every batch can be re-run.
##
## For each case <output folder>/case_NN.mat holds the batch inputs in the layout read by
## penicillium.BatchParameters.from_matlab (x0, alpha_kla, PAA_c, N_conc_paa and the eight dist* vectors), plus
## T, Ctrl_flags and the recorded channels (states, inputs, OUR, CER) as columns of `out` named in `out_names`.
##
## The setup block in run_case is adapted from IndPenSim V2.01 indpensim_run.m, Copyright (c) Newcastle University,
## University of Manchester and Perceptive Engineering, BSD 3-Clause License (LICENSE, part 2). No V2.01 file is
## distributed with Penicillium: download V2.01 from MATLAB File Exchange (49041) or industrialpenicillinsimulation.com.

1;

## id, Batch_no, Random_seed_ref, PRBS, variable length, fault, Raman_spec
CASES = [
   1   1  101  0  0  0  0
   2   2  202  0  0  0  1
   3   3  303  0  1  0  0
   4   4  404  0  0  1  0
   5   5  505  0  0  2  0
   6   6  606  0  0  3  0
   7   7  707  0  0  4  0
   8   8  808  0  0  5  0
   9   9  909  0  0  6  0
  10  10  110  0  0  7  0
  11  11  211  0  0  8  0
  12  12  312  1  0  0  0
  13  13  413  1  1  0  0
  14  14  514  0  0  0  2
  15  15  615  0  0  1  2
];

OUT_NAMES = {"S", "DO2", "O2", "P", "V", "Wt", "pH", "T", "Q", "Viscosity", "Culture_age", "a0", "a1", "a3", ...
             "a4", "n0", "n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9", "nm", "phi0", "CO2outgas", ...
             "CO2_d", "PAA", "NH3", "mu_P_calc", "mu_X_calc", "X", "Fg", "RPM", "Fpaa", "Fs", "Fa", "Fb", "Fc", ...
             "Foil", "Fh", "Fw", "pressure", "Fremoved", "OUR", "CER"};

function prepare_sources (src, dst)
  ## Copy V2.01 into dst and apply the Octave compatibility edits.
  if ! exist (dst, "dir")
    mkdir (dst);
  endif
  files = [dir(fullfile (src, "*.m")); dir(fullfile (src, "*.mat")); dir(fullfile (src, "*.txt"))];
  for i = 1:numel (files)  # read and write, as copyfile goes through xcopy on Windows and prompts
    fid = fopen (fullfile (src, files(i).name), "r");
    bytes = fread (fid, Inf, "*uint8");
    fclose (fid);
    fid = fopen (fullfile (dst, files(i).name), "w");
    fwrite (fid, bytes);
    fclose (fid);
  endfor
  ## V2.01 uses ode15s's defaults (RelTol 1e-3, AbsTol 1e-6). Setting RELTOL and ABSTOL in the environment
  ## overrides them, to compare at tolerances where the solver no longer matters.
  tolerances = "";
  if ! isempty (getenv ("RELTOL"))
    tolerances = sprintf (", 'RelTol', %s, 'AbsTol', %s", getenv ("RELTOL"), getenv ("ABSTOL"));
  endif
  ## PATCHES: {file, old text, new text, reason}
  patches = {
    "indpensim.m", ...
    "ode15s('indpensim_ode', t(k):h_ode:t(k+1), x00,[], u00, p);", ...
    ["ode15s(@(tt, yy) indpensim_ode(tt, yy, [], u00, p), t(k):h_ode:t(k+1), x00, " ...
     "odeset('InitialSlope', indpensim_ode(t(k), x00(:), [], u00, p)" tolerances "));"], ...
    ["Octave does not pass extra ode15s arguments in MATLAB's old (t, y, flag, p1, p2) form; and Octave's " ...
     "ode15s (SUNDIALS IDA) starts from a zero slope unless given one, where MATLAB's starts from f(t0, y0)"];
  };
  for i = 1:rows (patches)
    f = fullfile (dst, patches{i, 1});
    txt = fileread (f);
    if isempty (strfind (txt, patches{i, 2}))
      error ("patch %d: text not found in %s", i, patches{i, 1});
    endif
    fid = fopen (f, "w");
    fputs (fid, strrep (txt, patches{i, 2}, patches{i, 3}));
    fclose (fid);
  endfor
  ## smooth() is in MATLAB's Curve Fitting Toolbox, which Octave lacks: moving average whose span shrinks
  ## symmetrically at the ends, as MATLAB documents. Used only for the Raman baseline noise.
  fid = fopen (fullfile (dst, "smooth.m"), "w");
  fputs (fid, ["function yy = smooth (y, span)\n" ...
               "  y = y(:); n = numel (y); yy = zeros (n, 1); h = floor ((span - 1) / 2);\n" ...
               "  for i = 1:n\n" ...
               "    w = min ([h, i - 1, n - i]);\n" ...
               "    yy(i) = mean (y(i - w:i + w));\n" ...
               "  end\n" ...
               "end\n"]);
  fclose (fid);
endfunction

function run_case (c, outdir, out_names)
  [id, Batch_no, Random_seed_ref, prbs, variable, fault, raman] = num2cell (c){:};

  ## ---- Ctrl_flags as in indpensim_run.m
  Ctrl_flags.SBC = 0;
  Ctrl_flags.PRBS = prbs;
  Ctrl_flags.Fixed_Batch_length = variable;
  Ctrl_flags.IC = 0;
  Ctrl_flags.Inhib = 2;
  Ctrl_flags.Dis = 1;
  Ctrl_flags.Faults = fault;
  Ctrl_flags.Vis = 0;
  Ctrl_flags.Raman_spec = raman;
  Ctrl_flags.Batch_Num = Batch_no;
  Ctrl_flags.Off_line_m = 12;
  Ctrl_flags.Off_line_delay = 4;
  Ctrl_flags.plots = 0;

  ## ---- Random setup block of indpensim_run.m (V2.01), with Random_seed_ref given instead of ceil(rand*1000)
  Optimum_Batch_lenght = 230;
  if Ctrl_flags.Fixed_Batch_length == 1
    rng (Random_seed_ref);  # V2.01 draws this from the unseeded generator
    Batch_length_variation = 25*randn (1);
    T = round (Optimum_Batch_lenght + Batch_length_variation);
  else
    T = Optimum_Batch_lenght;
  endif
  Seed_ref = 31 + Random_seed_ref;
  Rand_ref = 1;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  intial_conds = 0.5+0.05*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.mux = 0.41+0.025*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.mup = 0.041+ 0.0025*randn;
  h = 0.2;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.S = 1 + 0.1*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.DO2 = 15 + 0.5*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.X = intial_conds + 0.1*randn;
  x0.P = 0;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.V = 5.800e+04 + 500*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.Wt = 6.2e+04 + 500*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.CO2outgas = 0.038 + 0.001*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.O2 = 0.20+ 0.05*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.pH = 6.5 + 0.1*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.T = 297+ 0.5*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.a0 = intial_conds*(1/3);
  x0.a1 = intial_conds*(2/3);
  x0.a3 = 0;
  x0.a4 = 0;
  x0.Culture_age = 0;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.PAA = 1400+50*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  x0.NH3 = 1700+50*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  alpha_kla = 85 + 10*randn;
  rng (Seed_ref+Batch_no+Rand_ref); Rand_ref = Rand_ref+1;
  PAA_c = 530000 + 20000*randn;
  rng (Seed_ref+Batch_no+Rand_ref);
  N_conc_paa = 2*75000 + 2000*randn;
  Batch_time = 0:h:T;
  Ctrl_flags.T_sp = 298;
  Ctrl_flags.pH_sp = 6.5;

  rng (Random_seed_ref+Batch_no);
  b1 = 1 - 0.995;
  a1 = [1 -0.995];
  n = round (T/h) + 1;  # V2.01 writes T/h+1; rounded so a non-integer float never reaches randn
  v = randn (n, 1); distMuP = filter (b1, a1, 0.03*v);
  Xinterp.distMuP = createChannel ('Penicillin specific growth rate disturbance', 'g/Lh', 'h', Batch_time, distMuP);
  v = randn (n, 1); distMuX = filter (b1, a1, 0.25*v);
  Xinterp.distMuX = createChannel ('Biomass specific  growth rate disturbance', 'hr^{-1}', 'h', Batch_time, distMuX);
  v = randn (n, 1); distcs = filter (b1, a1, 5*300*v);
  Xinterp.distcs = createChannel ('Substrate concentration disturbance ', ' g L^{-1}', 'h', Batch_time, distcs);
  v = randn (n, 1); distcoil = filter (b1, a1, 300*v);
  Xinterp.distcoil = createChannel ('Substrate concentration disturbance ', ' g L^{-1}', 'h', Batch_time, distcoil);
  v = randn (n, 1); distabc = filter (b1, a1, 0.2*v);
  Xinterp.distabc = createChannel ('Acid/Base concentration disturbance ', ' g L^{-1}', 'h', Batch_time, distabc);
  v = randn (n, 1); distPAA = filter (b1, a1, 300000*v);  # drawn twice in V2.01; the second draw is used
  v = randn (n, 1); distPAA = filter (b1, a1, 300000*v);
  Xinterp.distPAA = createChannel ('Phenylacetic acid concentration disturbance ', ' g L^{-1}', 'h', Batch_time, distPAA);
  v = randn (n, 1); distTcin = filter (b1, a1, 100*v);
  Xinterp.distTcin = createChannel ('Coolant inlet temperature disturbance ', 'K', 'h', Batch_time, distTcin);
  v = randn (n, 1); distO_2in = filter (b1, a1, 0.02*v);
  Xinterp.distO_2in = createChannel ('Oxygen inlet concentration', '%', 'h', Batch_time, distO_2in);

  ## ---- V2.01 model, controller and main loop, unchanged
  if raman == 2
    pkg load signal  # sgolayfilt, used by V2.01's PLS prediction of PAA (Substrate_prediction.m)
  endif
  par = Parameter_list (x0, alpha_kla, N_conc_paa, PAA_c);
  tic;
  Xref = indpensim (@fctrl_indpensim, Xinterp, x0, h, T, 2, par, Ctrl_flags);
  runtime_s = toc;

  out = zeros (numel (Xref.S.y), numel (out_names));
  for j = 1:numel (out_names)
    out(:, j) = Xref.(out_names{j}).y(:);
  endfor
  out_time = Xref.S.t(:);
  total_yield_kg = (Xref.V.y(end)*Xref.P.y(end) - sum (Xref.Fremoved.y .* Xref.P.y)*h) / 1000;
  octave_version = OCTAVE_VERSION;
  reltol = getenv ("RELTOL");  # empty: V2.01's ode15s defaults
  abstol = getenv ("ABSTOL");
  f = fullfile (outdir, sprintf ("case_%02d.mat", id));
  save ("-v7", f, "x0", "alpha_kla", "PAA_c", "N_conc_paa", "distMuP", "distMuX", "distcs", "distcoil", ...
        "distabc", "distPAA", "distTcin", "distO_2in", "T", "Ctrl_flags", "Random_seed_ref", "out", ...
        "out_names", "out_time", "total_yield_kg", "runtime_s", "octave_version", "reltol", "abstol");
  printf ("case %2d: T %g h, fault %d, Raman %d, PRBS %d: %.0f s, yield %.1f kg\n", id, T, fault, raman, prbs, ...
          runtime_s, total_yield_kg);
  fflush (stdout);
endfunction

args = argv ();
if numel (args) < 2
  error ("usage: run_indpensim_v201.m <IndPenSim_V2.01 folder> <output folder> [case ids]");
endif
outdir = args{2};
if ! exist (outdir, "dir")
  mkdir (outdir);
endif
srcdir = fullfile (outdir, "src");
prepare_sources (args{1}, srcdir);
addpath (srcdir);
warning ("off", "all");
ids = CASES(:, 1)';
if numel (args) > 2
  ids = cellfun (@str2double, args(3:end))(:)';  # argv is a column; `for` walks the columns
endif
for id = ids
  run_case (CASES(CASES(:, 1) == id, :), outdir, OUT_NAMES);
endfor
