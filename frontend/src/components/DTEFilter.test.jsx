import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import DTEFilter from './DTEFilter';

describe('DTEFilter', () => {
  test('emits null when input cleared', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={7} onChange={fn} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '' } });
    expect(fn).toHaveBeenCalledWith(null);
  });

  test('emits parsed number when valid input', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={null} onChange={fn} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '30' } });
    expect(fn).toHaveBeenCalledWith(30);
  });

  test('rejects out-of-range values above max', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={null} onChange={fn} max={365} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '99999' } });
    expect(fn).not.toHaveBeenCalled();
  });

  test('rejects negative values', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={null} onChange={fn} min={0} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '-5' } });
    expect(fn).not.toHaveBeenCalled();
  });

  test('displays current value', () => {
    const { getByLabelText } = render(<DTEFilter value={14} onChange={() => {}} />);
    expect(getByLabelText(/maximum days to expiry/i)).toHaveValue(14);
  });

  test('displays empty when value is null', () => {
    const { getByLabelText } = render(<DTEFilter value={null} onChange={() => {}} />);
    expect(getByLabelText(/maximum days to expiry/i)).toHaveValue(null);
  });

  test('accepts value at min boundary', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={null} onChange={fn} min={0} max={365} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '0' } });
    expect(fn).toHaveBeenCalledWith(0);
  });

  test('accepts value at max boundary', () => {
    const fn = jest.fn();
    const { getByLabelText } = render(<DTEFilter value={null} onChange={fn} min={0} max={365} />);
    fireEvent.change(getByLabelText(/maximum days to expiry/i), { target: { value: '365' } });
    expect(fn).toHaveBeenCalledWith(365);
  });
});
