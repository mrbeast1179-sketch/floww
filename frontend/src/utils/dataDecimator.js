/**
 * dataDecimator.js
 *
 * Utility for reducing data point density to maintain performance
 * with large datasets (10k+ points).
 *
 * Uses Largest Triangle Three Buckets (LTTB) algorithm for
 * visually accurate downsampling, plus simple interval decimation
 * for time-series data.
 */

/**
 * Simple interval-based decimation.
 * Keeps every Nth point, always includes first and last.
 *
 * @param {Array} data - Array of data points
 * @param {number} maxPoints - Maximum number of points to keep
 * @returns {Array} Decimated array
 */
export function decimateByInterval(data, maxPoints = 2000) {
  if (!data || data.length <= maxPoints) return data;
  if (!Array.isArray(data)) return data;

  const step = Math.ceil(data.length / maxPoints);
  const result = [];

  for (let i = 0; i < data.length; i += step) {
    result.push(data[i]);
  }

  // Always include last point
  if (result[result.length - 1] !== data[data.length - 1]) {
    result.push(data[data.length - 1]);
  }

  return result;
}

/**
 * Largest Triangle Three Buckets (LTTB) algorithm.
 * Preserves visual fidelity better than simple interval decimation.
 *
 * @param {Array} data - Array of objects with x, y properties
 * @param {number} maxPoints - Maximum number of points to keep
 * @returns {Array} Decimated array
 */
export function decimateLTTB(data, maxPoints = 2000) {
  if (!data || data.length <= maxPoints) return data;
  if (!Array.isArray(data) || data.length < 3) return data;

  const result = [];
  const bucketSize = (data.length - 2) / (maxPoints - 2);

  // Always keep first point
  result.push(data[0]);

  let prevIdx = 0;
  let avgIdx = 0;

  for (let i = 1; i < maxPoints - 1; i++) {
    // Calculate bucket boundaries
    const bucketStart = Math.floor((i - 1) * bucketSize) + 1;
    const bucketEnd = Math.min(Math.floor(i * bucketSize) + 1, data.length - 1);
    const nextBucketStart = Math.floor(i * bucketSize) + 1;
    const nextBucketEnd = Math.min(Math.floor((i + 1) * bucketSize) + 1, data.length - 1);

    // Calculate average point in next bucket
    let avgX = 0, avgY = 0;
    const nextCount = Math.max(nextBucketEnd - nextBucketStart, 1);
    for (let j = nextBucketStart; j < nextBucketEnd; j++) {
      avgX += data[j].x ?? data[j].strike ?? j;
      avgY += data[j].y ?? data[j].gex ?? data[j].value ?? 0;
    }
    avgX /= nextCount;
    avgY /= nextCount;

    // Find point in current bucket that forms largest triangle
    let maxArea = -1;
    let maxIdx = bucketStart;

    const prevPoint = data[prevIdx];
    const prevX = prevPoint.x ?? prevPoint.strike ?? prevIdx;
    const prevY = prevPoint.y ?? prevPoint.gex ?? prevPoint.value ?? 0;

    for (let j = bucketStart; j < bucketEnd; j++) {
      const currX = data[j].x ?? data[j].strike ?? j;
      const currY = data[j].y ?? data[j].gex ?? data[j].value ?? 0;

      // Triangle area
      const area = Math.abs(
        (prevX - currX) * (avgY - prevY) -
        (prevX - avgX) * (currY - prevY)
      );

      if (area > maxArea) {
        maxArea = area;
        maxIdx = j;
      }
    }

    result.push(data[maxIdx]);
    prevIdx = maxIdx;
  }

  // Always keep last point
  result.push(data[data.length - 1]);

  return result;
}

/**
 * Decimate heatmap data by time range.
 * Older time ranges get more aggressive decimation.
 *
 * @param {Array} data - Heatmap data (strike x expiry matrix)
 * @param {string} timeRange - '1D', '1W', '1M', '3M', 'ALL'
 * @returns {Array} Decimated data
 */
export function decimateHeatmapByRange(data, timeRange = '1D') {
  if (!data) return data;

  const limits = {
    '1D': 500,
    '1W': 1000,
    '1M': 2000,
    '3M': 3000,
    'ALL': 5000,
  };

  const maxPoints = limits[timeRange] || 2000;

  if (Array.isArray(data)) {
    return decimateLTTB(data, maxPoints);
  }

  // For grid/matrix data, decimate each row
  if (typeof data === 'object') {
    const result = {};
    for (const [key, value] of Object.entries(data)) {
      if (Array.isArray(value)) {
        result[key] = decimateByInterval(value, maxPoints);
      } else {
        result[key] = value;
      }
    }
    return result;
  }

  return data;
}

/**
 * Memoization helper for expensive calculations.
 * Caches results based on serialized arguments.
 *
 * @param {Function} fn - Function to memoize
 * @param {number} maxCacheSize - Max cache entries (default 100)
 * @returns {Function} Memoized function
 */
export function memoizeWithLimit(fn, maxCacheSize = 100) {
  const cache = new Map();

  return function(...args) {
    const key = JSON.stringify(args);

    if (cache.has(key)) {
      // Move to end (LRU)
      const value = cache.get(key);
      cache.delete(key);
      cache.set(key, value);
      return value;
    }

    const result = fn.apply(this, args);

    // Evict oldest if at capacity
    if (cache.size >= maxCacheSize) {
      const firstKey = cache.keys().next().value;
      cache.delete(firstKey);
    }

    cache.set(key, result);
    return result;
  };
}

/**
 * Estimate DOM node count for a dataset.
 * Useful for deciding whether decimation is needed.
 *
 * @param {Array} data - Data array
 * @param {number} nodesPerRow - Estimated DOM nodes per data row
 * @returns {number} Estimated DOM node count
 */
export function estimateDOMNodes(data, nodesPerRow = 5) {
  if (!data) return 0;
  if (Array.isArray(data)) return data.length * nodesPerRow;
  if (typeof data === 'object') {
    return Object.values(data).reduce((sum, v) => {
      return sum + (Array.isArray(v) ? v.length * nodesPerRow : 0);
    }, 0);
  }
  return 0;
}

/**
 * Auto-decimate based on estimated DOM nodes.
 * Returns original data if under threshold, decimated otherwise.
 *
 * @param {Array} data - Data array
 * @param {number} maxNodes - Max DOM nodes before decimation (default 5000)
 * @param {number} nodesPerRow - Estimated nodes per row
 * @returns {Array} Original or decimated data
 */
export function autoDecimate(data, maxNodes = 5000, nodesPerRow = 5) {
  if (!data || !Array.isArray(data)) return data;
  const estimated = data.length * nodesPerRow;
  if (estimated <= maxNodes) return data;

  const targetPoints = Math.ceil(maxNodes / nodesPerRow);
  return decimateLTTB(data, targetPoints);
}
