import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import ExpiryFilter from './ExpiryFilter';

describe('ExpiryFilter', () => {
  test('renders all expiries as options plus All', () => {
    const { getAllByRole } = render(
      <ExpiryFilter expiries={['2026-05-30', '2026-06-06']} value={null} onChange={() => {}} />
    );
    const opts = getAllByRole('option');
    expect(opts.length).toBe(3); // 2 + "All expiries"
  });

  test('shows empty state when no expiries', () => {
    const { container } = render(
      <ExpiryFilter expiries={[]} value={null} onChange={() => {}} />
    );
    expect(container.textContent).toMatch(/no expiries/i);
  });

  test('emits null when "All" selected', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(
      <ExpiryFilter expiries={['2026-05-30']} value="2026-05-30" onChange={fn} />
    );
    fireEvent.change(getByLabelText(/filter by expiry/i), { target: { value: '__all__' } });
    expect(fn).toHaveBeenCalledWith(null);
  });

  test('emits selected expiry on change', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(
      <ExpiryFilter expiries={['2026-05-30', '2026-06-06']} value={null} onChange={fn} />
    );
    fireEvent.change(getByLabelText(/filter by expiry/i), { target: { value: '2026-06-06' } });
    expect(fn).toHaveBeenCalledWith('2026-06-06');
  });

  test('renders expiry dates in options', () => {
    const { getByText } = render(
      <ExpiryFilter expiries={['2026-05-30', '2026-06-06']} value={null} onChange={() => {}} />
    );
    expect(getByText('2026-05-30')).toBeInTheDocument();
    expect(getByText('2026-06-06')).toBeInTheDocument();
  });
});
