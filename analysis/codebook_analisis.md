# Codebook — Anemia Supplementation Analysis

> Dataset: `anemia_valor.dta` (**ENDES 2024**) · N = 14 428 · 127 columns · SEED = 20260710
> (Verificado: `v008` CMC 1489–1500 ↔ enero–diciembre 2024 en los 14 428 casos; etiqueta anterior "ENDES 2023" era heredada del repo original y era incorrecta.)

---

## Sample Flow

```
14 428  (ENDES total)
   ↓ received_any = 1
 9 079  (≥1 supplement received in 12 m)
   ↓ dx_anemia = 0
 6 908  (no prior anemia diagnosis)
   ↓ complete cases
 6 703  (confirmatory sample)
   ├── 2 194 exposed (any toma7d_* = 1; equivalent to T5 ≥ 1)
   └── 4 509 unexposed (all toma7d_* = 0; T5 = 0)
```

Paper exposure (body): reported consumption of at least one of `toma7d_jar/got/pol/otr` in the previous 7 days. `T5 ≥ 1` coincides with that dichotomy in the analytic sample; the ordinal value 5 is not used.

Missing excluded: `eda_aun` (86.7 % missing), `lact_exclu` (43.3 % missing).

---

## Treatment Variables (T)

| Variable | Description | Type | Role | Missing | Notes |
|---|---|---|---|---|---|
| `T1` | Received ≥1 supplement type in 12 months | binary (0/1) | T | 0 | N = 9 079 yes |
| `T2` | Received supplements (alternate definition) | binary (0/1) | T | 0 | N = 3 752 yes |
| `T3` | Consumed any supplement in last 7 days (short-term proxy) | binary (0/1) | T | 0 | N = 3 184 yes; used as null-effect placebo |
| `T4` | Number of supplement types received | ordinal (0–5) | T | 0 | Freq: 5 349 / 4 087 / 2 135 / 346 / 9 / 2 502 |
| `T5` | Consumption intensity index (microdata) | ordinal (0–5) | historical T | 0 | Not interpreted in the paper. Dichotomy T5≥1 matches any `toma7d_*`. Value 5 unused. |
| `n_consumidos` | Number of supplement types consumed (past 7 days) | ordinal (0–3) | T | 0 | Freq: 10 676 / 3 683 / 66 / 3. Constructed from 4 supplement type dummies |
| `n_recibidos` | Number of supplement types received | ordinal (0–4) | T | 0 | Freq: 5 349 / 6 577 / 2 224 / 277 / 1 |
| `total_toma` | Total quantity consumed (all types, 7 days) | continuous (0–360) | T | 0 | Sum across 4 supplement types |
| `total_rec` | Total quantity received (all types, 12 months) | continuous (0–360) | T | 0 | Sum across 4 supplement types |
| `intensidad` | Delivery intensity index | continuous (~0.17–1.33) | T | 0 | Mean ≈ 1.12 |
| `rec12m_jar` | Received jarabe in 12 months | binary (0/1) | T | 0 | |
| `rec12m_got` | Received gotas in 12 months | binary (0/1) | T | 0 | |
| `rec12m_pol` | Received polvo in 12 months | binary (0/1) | T | 0 | |
| `rec12m_otr` | Received otro in 12 months | binary (0/1) | T | 0 | |
| `toma7d_jar` | Consumed jarabe in last 7 days | binary (0/1) | T | 0 | |
| `toma7d_got` | Consumed gotas in last 7 days | binary (0/1) | T | 0 | |
| `toma7d_pol` | Consumed polvo in last 7 days | binary (0/1) | T | 0 | |
| `toma7d_otr` | Consumed otro in last 7 days | binary (0/1) | T | 0 | |
| `qtoma12m_jar` | Quantity consumed — jarabe (12 months) | count | T | 0 | |
| `qtoma12m_got` | Quantity consumed — gotas (12 months) | count | T | 0 | |
| `qtoma12m_pol` | Quantity consumed — polvo (12 months) | count | T | 0 | |
| `qtoma12m_otr` | Quantity consumed — otro (12 months) | count | T | 0 | |

---

## Outcome Variables (Y)

| Variable | Description | Type | Role | Missing | Notes |
|---|---|---|---|---|---|
| `anemia` | Binary anemia (Hb < MINSA threshold) | binary (0/1) | Y₁ | 0 | 37.9 % in confirmatory sample |
| `anemia_modsev` | Moderate or severe anemia | binary (0/1) | Y₂ | 0 | Constructed as `niveles_anemia == 2` |
| `hb_minsa` | Hemoglobin, altitude-adjusted (MINSA) | continuous (g/L) | Y₃ | 0 | Mean ≈ 112.44 |
| `hb_oms` | Hemoglobin, altitude-adjusted (OMS) | continuous (g/L) | Y₃ | 0 | Mean ≈ 111.87 |
| `sev_anemia_score` | Anemia severity ordinal score | ordinal (0–2) | Y₄ | 0 | Derived from `niveles_anemia` |
| `niveles_anemia` | Anemia severity (original) | ordinal (0–2) | — | 0 | 0 = none, 1 = mild, 2 = moderate/severe |

> **Hb scale**: g/L. Population mean ~112. ±0.76 g/L = ±0.076 g/dL.

---

## Covariates (X)

| Variable | Description | Type | Role | Missing | Notes |
|---|---|---|---|---|---|
| `edad_niño` | Child age (months) | continuous | X | 0 | 6–35 months range |
| `niña` | Female child | binary (0/1) | X | 0 | |
| `bajo_peso` | Low birth weight (analysis binary) | binary (0/1) | X | 0 | Built from `bajo_peso_r` (not raw DHS 1/2/3 `bajo_peso`) |
| `bajo_peso_r` | Low birth weight recode | binary (0/1) | X | 0 | Preferred binary; 1 = LBW |
| `edad_madre` | Maternal age (years) | continuous | X | 0 | |
| `educa_madre` | Maternal education level | ordinal | X | 0 | |
| `madre_anemia` | Maternal anemia | binary (0/1) | X | 449 (3.1 %) | |
| `control_pren` | Prenatal care received | binary (0/1) | X | 0 | |
| `quintil` | Wealth quintile | ordinal (1–5) | X | 0 | |
| `agua_potable` | Potable water access | binary (0/1) | X | 0 | |
| `saneamiento` | Sanitation access | binary (0/1) | X | 0 | |
| `area` | Urban residence | binary (0/1) | X | 0 | 1 = Urban, 0 = Rural |
| `dpto` | Department code | categorical (25 values) | X | 0 | For geographic heterogeneity |
| `trata_parasito` | Parasite treatment received | binary (0/1) | X | 0 | Candidate covariate / negative control |

### Excluded from Propensity Score

| Variable | Description | Type | Role | Missing | Notes |
|---|---|---|---|---|---|
| `eda_14d_ant` | Diarrhea in last 14 days | binary (0/1) | post-T | 0 | Post-treatment → excluded from PS model |

---

## Selection / Exclusion Variables

| Variable | Description | Type | Role | Missing | Notes |
|---|---|---|---|---|---|
| `received_any` | Received any supplement | binary (0/1) | exclusion | 0 | `T1 == 1` or `n_recibidos ≥ 1` or `total_rec > 0`; N = 9 079 |
| `dx_anemia` | Prior child anemia diagnosis | binary (0/1) | exclusion | 0 | N = 3 128 yes. NOT the same as `madre_anemia` |
| `dx_sustento` | Documentation of anemia diagnosis | — | exclusion | — | |
| `eda_aun` | Currently has diarrhea | binary (0/1) | exclusion | 12 506 (86.7 %) | Excluded from confirmatory sample |
| `lact_exclu` | Exclusive breastfeeding | binary (0/1) | exclusion | 6 245 (43.3 %) | Excluded from confirmatory sample |

---

## Design / Survey Variables

| Variable | Description | Type | Role | Notes |
|---|---|---|---|---|
| `hv005` | Sampling weight (scale ×1e6) | continuous | design | Normalize to `/1e6` before use |
| `hv001` | Primary sampling unit / cluster | categorical (3 193 unique) | design | Used for cluster-robust SE and stratified bootstrap |
| `hv022` | Stratum | categorical (240 unique) | design | Used for stratified bootstrap |
| `hv021` | — | — | — | **Not available** in dataset |
| `hv023` | — | — | — | **Not available** in dataset |

---

## Conventions

- **SEED**: `20260710` (all random operations).
- **Hb units**: g/L throughout. Multiply by 0.1 for g/dL.
- **Primary exposure (paper)**: any of `toma7d_jar/got/pol/otr` in the previous 7 days. Equivalent to `T5 ≥ 1` in the analytic sample; do not interpret the T5 ordinal scale.
- **Primary Y**: `anemia_modsev` (moderate or severe anemia).
- **Estimator**: IPW × design weights (primary); AIPW / matching only in supplement.
- **Inference (body)**: stratified cluster bootstrap, 2000 replicates (`hv001` within `hv022`). Source of truth: `paper/tablas/tabla_sensibilidades_cuerpo.csv`. The 500-replicate IC in `resumen_final.json` is historical and must not be cited in the article.
- **Balance**: max \|SMD\| ≈ 0.039 after weighting (threshold < 0.10).
- **Missing data**: Complete-case primary; treating the 2 analytic missing intake values as non-consumption does not change the estimate.
