import React from 'react';

/**
 * Drop-down for selecting an option expiry from the available chain.
 *
 * Props:
 *   expiries: string[]   — list of YYYY-MM-DD strings
 *   value: string | null  — currently selected expiry
 *   onChange: (string|null) => void
 */
export default function ExpiryFilter({ expiries = [], value, onChange }) {
  if (!Array.isArray(expiries) || expiries.length === 0) {
    return <span className="expiry-filter expiry-filter--empty">No expiries</span>;
  }

  const handleChange = (e) => {
    const v = e.target.value;
    onChange(v === '__all__' ? null : v);
  };

  return (
    <select
      className="expiry-filter"
      value={value || '__all__'}
      onChange={handleChange}
      aria-label="Filter by expiry"
    >
      <option value="__all__">All expiries</option>
      {expiries.map((exp) => (
        <option key={exp} value={exp}>
          {exp}
        </option>
      ))}
    </select>
  );
}
