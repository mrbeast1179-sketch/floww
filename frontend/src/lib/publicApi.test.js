import axios from "axios";
import { fetchPublicChain, fetchPublicQuote, publicChainUrl, publicQuoteUrl } from "./publicApi";

jest.mock("axios");

describe("public API helpers", () => {
  beforeEach(() => jest.clearAllMocks());

  test("builds an encoded chain URL with query parameters", () => {
    expect(publicChainUrl("^spx", { expiration: "2026-09-18", expirations: 2 }))
      .toContain("/api/public/chain/%5ESPX?expiration=2026-09-18&expirations=2");
  });

  test("uses four expirations by default", () => {
    expect(publicChainUrl("spy")).toContain("/api/public/chain/SPY?expirations=4");
  });

  test("builds a quote URL", () => {
    expect(publicQuoteUrl("spy")).toContain("/api/public/quotes/SPY");
  });

  test("fetches a chain and forwards options", async () => {
    axios.get.mockResolvedValue({ data: { ticker: "SPY", contracts: [] } });
    const signal = {};
    const result = await fetchPublicChain("SPY", {
      expiration: "2026-09-18",
      expirations: 1,
      signal,
      timeout: 1234,
    });

    expect(result.ticker).toBe("SPY");
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining("/api/public/chain/SPY?expiration=2026-09-18&expirations=1"),
      { signal, timeout: 1234 },
    );
  });

  test("fetches a quote with the default timeout", async () => {
    axios.get.mockResolvedValue({ data: { ticker: "SPY", spot: 500 } });
    await expect(fetchPublicQuote("SPY")).resolves.toEqual({ ticker: "SPY", spot: 500 });
    expect(axios.get).toHaveBeenCalledWith(
      expect.stringContaining("/api/public/quotes/SPY"),
      { signal: undefined, timeout: 10000 },
    );
  });
});
