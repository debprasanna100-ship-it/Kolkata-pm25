"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchMetrics,
  fetchAttributionSummary,
  fetchProxyAgreement,
  fetchSeasonalImportance,
  fetchGlobalImportance,
  fetchProxyPrevalence,
  fetchPredictions,
} from "@/lib/data";

/**
 * TanStack Query hooks for all dashboard artifacts.
 * Replaces the manual useEffect + useState pattern in page.tsx with
 * declarative, cached, background-refreshing queries.
 */

export function useMetrics() {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: fetchMetrics,
    staleTime: Infinity, // artifacts only change on retrain
  });
}

export function useAttributionSummary() {
  return useQuery({
    queryKey: ["attribution-summary"],
    queryFn: fetchAttributionSummary,
    staleTime: Infinity,
  });
}

export function useProxyAgreement() {
  return useQuery({
    queryKey: ["proxy-agreement"],
    queryFn: fetchProxyAgreement,
    staleTime: Infinity,
  });
}

export function useSeasonalImportance() {
  return useQuery({
    queryKey: ["seasonal-importance"],
    queryFn: fetchSeasonalImportance,
    staleTime: Infinity,
  });
}

export function useGlobalImportance() {
  return useQuery({
    queryKey: ["global-importance"],
    queryFn: fetchGlobalImportance,
    staleTime: Infinity,
  });
}

export function useProxyPrevalence() {
  return useQuery({
    queryKey: ["proxy-prevalence"],
    queryFn: fetchProxyPrevalence,
    staleTime: Infinity,
  });
}

export function usePredictions() {
  return useQuery({
    queryKey: ["predictions"],
    queryFn: fetchPredictions,
    staleTime: Infinity,
  });
}
