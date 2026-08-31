import axios from "axios";
import { API } from "../config/api";

export function publicChainUrl(ticker, { expiration, expirations = 4 } = {}) {
  const params = new URLSearchParams();
  if (expiration) params.set("expiration", expiration);
  if (expirations != null) params.set("expirations", String(expirations));
  const query = params.toString();
  return `${API}/public/chain/${encodeURIComponent(String(ticker).toUpperCase())}${query ? `?${query}` : ""}`;
}

export function publicQuoteUrl(ticker) {
  return `${API}/public/quotes/${encodeURIComponent(String(ticker).toUpperCase())}`;
}

export async function fetchPublicChain(ticker, options = {}) {
  const { signal, timeout = 20000, ...query } = options;
  const response = await axios.get(publicChainUrl(ticker, query), { signal, timeout });
  return response.data;
}

export async function fetchPublicQuote(ticker, options = {}) {
  const { signal, timeout = 10000 } = options;
  const response = await axios.get(publicQuoteUrl(ticker), { signal, timeout });
  return response.data;
}
