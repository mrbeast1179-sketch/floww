import React from 'react';

/**
 * Numeric input for max days-to-expiry filter.
 *
 * Props:
 *   value: number | null   — current max DTE (null = no limit)
 *   onChange: (number|null) => void
 *   min: number  — default 0
 *   max: number  — default 365
 */
export default function DTEFilter({ value, onChange, min = 0, max = 365 }) {
  const display = value == null ? '' : String(value);

  const handleChange = (e) => {
    const raw = e.target.value.trim();
    if (raw === '') { onChange(null); return; }
    const n = parseInt(raw, 10);
    if (Number.isFinite(n) && n >= min && n <= max) onChange(n);
  };

  return (
    <label className="dte-filter">
      Max DTE:
      <input
        type="number" min={min} max={max} value={display}
        onChange={handleChange} placeholder="any"
        aria-label="Maximum days to expiry"
      />
    </label>
  );
}
