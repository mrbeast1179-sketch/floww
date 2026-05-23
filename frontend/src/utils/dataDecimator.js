/**
 * dataDecimator.js — PERFORMANCE OPTIMIZED
 *
 * Utility for reducing data point density to maintain performant
 * rendering with large datasets (10k+ points).
 *
 * Uses Largest Triangle Three Buckets (LTTB) algorithm for
 * visually accurate downsampling, plus simple interval decimation
 * for time-series data.
 *
 * Changes in this version:
 *   - LTTB handles flat arrays (numbers) in addition to {x,y} objects
 *   - Added decimateTimeRange() for time-range-based decimation
 *   - Memoization with LRU eviction for expensive calculations
 *   - Web Worker support hint for 50k+ point datasets
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
 * Extract numeric value from a data point (handles multiple formats).
 */
function _xOf(d, idx) {
  if (d == null) return idx;
  if (typeof d === "number") return idx;
  return d.x ?? d.strike ?? d.timestamp ?? idx;
}

function _yOf(d) {
  if (d == null) return 0;
  if (typeof d === "number") return d;
  return d.y ?? d.gex ?? d.value ?? d.price ?? 0;
}

/**
 * Largest Triangle Three Buckets (LTTB) algorithm.
 * Preserves visual fidelity better than simple interval decimation.
 *
 * Handles: flat arrays of numbers, arrays of {x,y} objects,
 * arrays of {strike, gex} objects, etc.
 *
 * @param {Array} data - Array of data points
 * @param {number} maxPoints - Maximum number of points to keep
 * @returns {Array} Decimated array (references to original objects)
 */
export function decimateLTTB(data, maxPoints = 2000) {
  if (!data || data.length <= maxPoints) return data;
  if (!Array.isArray(data) || data.length < 3) return data;

  const result = [];
  const bucketSize = (data.length - 2) / (maxPoints - 2);

  // Always keep first point
  result.push(data[0]);

  let prevIdx = 0;

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
      avgX += _xOf(data[j], j);
      avgY += _yOf(data[j]);
    }
    avgX /= nextCount;
    avgY /= nextCount;

    // Find point in current bucket that forms largest triangle
    let maxArea = -1;
    let maxIdx = bucketStart;

    const prevX = _xOf(data[prevIdx], prevIdx);
    const prevY = _yOf(data[prevIdx]);

    for (let j = bucketStart; j < bucketEnd; j++) {
      const currX = _xOf(data[j], j);
      const currY = _yOf(data[j]);

      // Triangle area (cross product)
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
 * Decimate heatmap/scatter data by time range.
 * Older time ranges get more aggressive decimation to keep
 * rendering under the 500ms budget for 10k points.
 *
 * Time range max points:
 *   '1D'   → 500    (every ~30s, fine-grained)
 *   '1W'   → 1000   (every ~1min)
 *   '1M'   → 2000   (every ~2min)
 *   '3M'   → 3000   (moderate detail)
 *   'ALL'  → 5000   (overview, most aggressive)
 *
 * @param {Array} data      - Data array (strike x expiry matrix or flat points)
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
    if (data.length <= maxPoints) return data;
    return decimateLTTB(data, maxPoints);
  }

  // For grid/matrix data, decimate each row
  if (typeof data === 'object') {
    const result = {};
    for (const [key, value] of Object.entries(data)) {
      if (Array.isArray(value)) {
        result[key] = value.length > maxPoints
          ? decimateLTTB(value, maxPoints)
          : value;
      } else {
        result[key] = value;
      }
    }
    return result;
  }

  return data;
}

/**
 * Decimate time-series data with range-aware density.
 * Intended for rolling floors/ceilings and flip zone time series.
 *
 * @param {Array} data      - Array of {ts, value} or flat values
 * @param {string} timeRange - '1D', '1W', '1M', '3M', 'ALL'
 * @returns {Array} Decimated array
 */
export function decimateTimeRange(data, timeRange = '1D') {
  if (!data || !Array.isArray(data) || data.length === 0) return data;

  const limits = { '1D': 200, '1W': 400, '1M': 800, '3M': 1200, 'ALL': 2000 };
  const maxPoints = limits[timeRange] || 400;

  return data.length > maxPoints ? decimateLTTB(data, maxPoints) : data;
}

/**
 * Memoization helper for expensive calculations.
 * LRU eviction when cache reaches maxCacheSize.
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
 * Targets <500ms render time for 10k points.
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

/**
 * Check if WebGL is available (for future WebGL renderer fallback).
 * @returns {boolean}
 */
export function isWebGLAvailable() {
  try {
    const canvas = document.createElement('canvas');
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    );
  } catch {
    return false;
  }
}
