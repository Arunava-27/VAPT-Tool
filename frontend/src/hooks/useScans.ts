import { useDispatch, useSelector } from 'react-redux';
import type { RootState, AppDispatch } from '../store';
import { setScans, setLoading, setError } from '../store/slices/scansSlice';
import { listScans } from '../api/scans';
import { useCallback } from 'react';

export function useScans() {
  const dispatch = useDispatch<AppDispatch>();
  const { scans, selectedScan, isLoading, error, total } = useSelector(
    (state: RootState) => state.scans
  );

  const fetchScans = useCallback(
    async (params?: { status?: string; limit?: number; offset?: number }) => {
      dispatch(setLoading(true));
      try {
        const response = await listScans(params);
        const data = Array.isArray(response.data) ? response.data : [];
        dispatch(setScans({ scans: data, total: data.length }));
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch scans';
        dispatch(setError(message));
      } finally {
        dispatch(setLoading(false));
      }
    },
    [dispatch]
  );

  return { scans, selectedScan, isLoading, error, total, fetchScans };
}
