import { spreadPosition } from '../pulse/spreadPosition.js';

describe('spreadPosition', () => {
  it('midpoint is MID ~0.5', () => {
    const r = spreadPosition(1.2, 1.0, 1.4);
    expect(r.position).toBeCloseTo(0.5, 2);
    expect(r.side).toBe('MID');
  });
  it('near bid is BID', () => {
    expect(spreadPosition(1.05, 1.0, 1.4).side).toBe('BID');
  });
  it('near ask is ASK', () => {
    expect(spreadPosition(1.35, 1.0, 1.4).side).toBe('ASK');
  });
  it('exact 0.33 is BID, 0.67 is ASK (boundary)', () => {
    // pos = (last-bid)/(ask-bid) => last = bid + pos*(ask-bid)
    // bid 1.0 ask 1.3 => spread 0.3
    expect(spreadPosition(1.099, 1.0, 1.3).side).toBe('BID'); // 0.33
    expect(spreadPosition(1.201, 1.0, 1.3).side).toBe('ASK'); // 0.67
  });
  it('NO_QUOTE when missing bid/ask or ask<=bid', () => {
    expect(spreadPosition(1.2, null, 1.4).side).toBe('NO_QUOTE');
    expect(spreadPosition(1.2, 1.0, null).side).toBe('NO_QUOTE');
    expect(spreadPosition(1.2, 1.5, 1.4).side).toBe('NO_QUOTE');
    expect(spreadPosition(1.2, 1.4, 1.4).side).toBe('NO_QUOTE');
  });
  it('clamps to [0,1]', () => {
    expect(spreadPosition(0.5, 1.0, 1.4).position).toBe(0);
    expect(spreadPosition(2.0, 1.0, 1.4).position).toBe(1);
  });
  it('fixtures: pulseRows honest states (8 rows)', async () => {
    const rows = (await import('../fixtures/pulseRows.json')).default;
    expect(rows).toHaveLength(8);
    // at least 3 NO_QUOTE
    const noqs = rows.filter((r) => spreadPosition(r.last, r.bid, r.ask).side === 'NO_QUOTE');
    expect(noqs.length).toBeGreaterThanOrEqual(3);
  });
});
