/**
 * Koinly API Scraper
 *
 * Runs in the browser console while logged into Koinly.
 * Uses the internal Koinly API (api.koinly.io) to extract wallets and
 * transactions, then downloads them as CSV files.
 *
 * Usage:
 *   1. Log into https://app.koinly.io
 *   2. Navigate to any page (e.g., /p/transactions)
 *   3. Open DevTools (F12) > Console
 *   4. Paste this entire script and press Enter
 *   5. Wait ~30-60 seconds for it to finish
 *
 * The script will automatically:
 *   - Capture your auth tokens from the SPA
 *   - Fetch all wallets and transactions via the API
 *   - Download two CSV files:
 *       koinly_wallets.csv
 *       koinly_transactions.csv
 *
 * How auth works:
 *   The SPA sends requests to api.koinly.io with X-Auth-Token and
 *   X-Portfolio-Token headers. We intercept these by monkey-patching
 *   XMLHttpRequest.setRequestHeader, then trigger a page navigation
 *   to force the SPA to make an API call we can capture.
 */

(async function koinlyAPIScraper() {
  'use strict';

  const CONFIG = {
    API_BASE: 'https://api.koinly.io',
    PER_PAGE: 100,         // max transactions per API page
    REQUEST_DELAY_MS: 500, // delay between API requests
    MAX_RETRIES: 3,
    RETRY_DELAY_MS: 3000,
  };

  // -------------------------------------------------------------------------
  // Utilities
  // -------------------------------------------------------------------------

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function escapeCSV(val) {
    if (val == null) return '';
    const str = String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return '"' + str.replace(/"/g, '""') + '"';
    }
    return str;
  }

  function toCSVRow(fields) {
    return fields.map(escapeCSV).join(',');
  }

  function downloadCSV(filename, csvContent) {
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function formatDate(isoStr) {
    if (!isoStr) return '';
    return new Date(isoStr).toISOString().replace('T', ' ').replace(/\.\d+Z/, ' UTC');
  }

  // -------------------------------------------------------------------------
  // Auth token capture
  // -------------------------------------------------------------------------

  /**
   * Capture the X-Auth-Token and X-Portfolio-Token that the Koinly SPA
   * sends to api.koinly.io. We monkey-patch XMLHttpRequest to intercept
   * headers, then trigger a SPA navigation to force an API call.
   */
  async function captureAuthTokens() {
    console.log('[Koinly Scraper] Capturing auth tokens...');

    const tokens = { authToken: null, portfolioToken: null };

    // Monkey-patch XHR to capture headers
    const origSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
      if (name === 'X-Auth-Token') tokens.authToken = value;
      if (name === 'X-Portfolio-Token') tokens.portfolioToken = value;
      return origSetRequestHeader.call(this, name, value);
    };

    // Trigger a SPA navigation to force an API call
    const goInput = document.querySelector('input[type="number"]');
    const goButton = [...document.querySelectorAll('button')].find(
      el => el.textContent?.trim() === 'Go'
    );

    if (goInput && goButton) {
      const nativeSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
      ).set;
      nativeSetter.call(goInput, '1');
      goInput.dispatchEvent(new Event('input', { bubbles: true }));
      goInput.dispatchEvent(new Event('change', { bubbles: true }));
      goButton.click();
    } else {
      // Try clicking a pagination link
      const pageLink = [...document.querySelectorAll('a')].find(
        a => a.href?.includes('page=') && a.textContent?.trim().match(/^\d+$/)
      );
      if (pageLink) pageLink.click();
    }

    // Wait for the SPA to make the API call
    for (let i = 0; i < 20; i++) {
      await sleep(500);
      if (tokens.authToken && tokens.portfolioToken) break;
    }

    // Restore original XHR
    XMLHttpRequest.prototype.setRequestHeader = origSetRequestHeader;

    if (!tokens.authToken || !tokens.portfolioToken) {
      throw new Error(
        'Could not capture auth tokens. Make sure you are on the Transactions page ' +
        'with pagination visible, or provide tokens manually.'
      );
    }

    console.log('[Koinly Scraper] Auth tokens captured successfully');
    return tokens;
  }

  // -------------------------------------------------------------------------
  // API Client
  // -------------------------------------------------------------------------

  function createAPIClient(tokens) {
    return async function apiGet(path, params) {
      const url = new URL(`${CONFIG.API_BASE}${path}`);
      if (params) {
        Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
      }

      for (let attempt = 1; attempt <= CONFIG.MAX_RETRIES; attempt++) {
        try {
          const resp = await fetch(url.toString(), {
            headers: {
              'Accept': 'application/json',
              'X-Auth-Token': tokens.authToken,
              'X-Portfolio-Token': tokens.portfolioToken,
            },
          });

          if (resp.status === 401) {
            throw new Error('401 Unauthorized - auth tokens expired. Re-login and try again.');
          }
          if (resp.status === 429) {
            const retryAfter = parseInt(resp.headers.get('Retry-After') || CONFIG.RETRY_DELAY_MS);
            console.warn(`[Koinly Scraper] Rate limited. Waiting ${retryAfter}ms...`);
            await sleep(retryAfter);
            continue;
          }
          if (!resp.ok) {
            throw new Error(`API returned ${resp.status}`);
          }

          return await resp.json();
        } catch (err) {
          if (attempt === CONFIG.MAX_RETRIES) throw err;
          console.warn(`[Koinly Scraper] Retry ${attempt}/${CONFIG.MAX_RETRIES}: ${err.message}`);
          await sleep(CONFIG.RETRY_DELAY_MS);
        }
      }
    };
  }

  // -------------------------------------------------------------------------
  // Extraction
  // -------------------------------------------------------------------------

  async function extractWallets(apiGet) {
    console.log('[Koinly Scraper] Extracting wallets...');
    const data = await apiGet('/api/wallets', { per_page: 100 });
    const wallets = data.wallets || [];
    console.log(`[Koinly Scraper] Found ${wallets.length} wallets`);
    return wallets;
  }

  async function extractTransactions(apiGet) {
    console.log('[Koinly Scraper] Extracting transactions...');

    // First page to get pagination info
    const firstPage = await apiGet('/api/transactions', {
      per_page: CONFIG.PER_PAGE,
      page: 1,
      order: 'date',
    });

    const totalPages = firstPage.meta?.page?.total_pages || 1;
    const totalItems = firstPage.meta?.page?.total_items || 0;
    console.log(`[Koinly Scraper] Total: ${totalItems} transactions across ${totalPages} pages`);

    let allTransactions = firstPage.transactions || [];
    console.log(`[Koinly Scraper] Page 1/${totalPages} - ${allTransactions.length} transactions`);

    // Scrape remaining pages
    const errors = [];
    for (let page = 2; page <= totalPages; page++) {
      await sleep(CONFIG.REQUEST_DELAY_MS);

      try {
        const data = await apiGet('/api/transactions', {
          per_page: CONFIG.PER_PAGE,
          page,
          order: 'date',
        });
        const pageTxns = data.transactions || [];
        allTransactions = allTransactions.concat(pageTxns);

        if (page % 5 === 0 || page === totalPages) {
          console.log(
            `[Koinly Scraper] Page ${page}/${totalPages} - ${allTransactions.length} transactions`
          );
        }
      } catch (err) {
        console.error(`[Koinly Scraper] Error on page ${page}: ${err.message}`);
        errors.push({ page, error: err.message });
      }
    }

    if (errors.length > 0) {
      console.warn(`[Koinly Scraper] ${errors.length} pages had errors:`, errors);
    }

    console.log(`[Koinly Scraper] Extraction complete: ${allTransactions.length} transactions`);
    return allTransactions;
  }

  // -------------------------------------------------------------------------
  // CSV Generation
  // -------------------------------------------------------------------------

  function walletsToCSV(wallets) {
    const headers = [
      'Koinly ID', 'Name', 'Type', 'Blockchain', 'Address', 'Balance Count',
    ];
    const rows = wallets.map(w => toCSVRow([
      w.id,
      w.name,
      w.wallet_type || '',
      w.blockchain || '',
      w.address || '',
      (w.balances || []).length,
    ]));
    return [toCSVRow(headers), ...rows].join('\n');
  }

  function transactionsToCSV(transactions) {
    const headers = [
      'Date',
      'Sent Amount', 'Sent Currency',
      'Received Amount', 'Received Currency',
      'Fee Amount', 'Fee Currency',
      'Net Worth Amount', 'Net Worth Currency',
      'Label', 'Description',
      'TxHash', 'Koinly ID',
      'From Wallet', 'From Wallet ID',
      'To Wallet', 'To Wallet ID',
    ];

    const rows = transactions.map(tx => {
      const from = tx.from || {};
      const to = tx.to || {};
      const fee = tx.fee || {};

      return toCSVRow([
        formatDate(tx.date),
        from.amount || '',
        from.currency?.symbol || '',
        to.amount || '',
        to.currency?.symbol || '',
        fee.amount || '',
        fee.currency?.symbol || '',
        tx.net_value || '',
        'USD',
        tx.type || '',
        tx.description || '',
        tx.txhash || '',
        tx.id || '',
        from.wallet?.name || '',
        from.wallet?.id || '',
        to.wallet?.name || '',
        to.wallet?.id || '',
      ]);
    });

    return [toCSVRow(headers), ...rows].join('\n');
  }

  // -------------------------------------------------------------------------
  // Main
  // -------------------------------------------------------------------------

  try {
    console.log('='.repeat(60));
    console.log('[Koinly Scraper] Starting API-based extraction...');
    console.log('='.repeat(60));

    const startTime = Date.now();

    // Step 1: Capture auth tokens
    const tokens = await captureAuthTokens();
    const apiGet = createAPIClient(tokens);

    // Step 2: Extract wallets
    const wallets = await extractWallets(apiGet);

    // Step 3: Extract transactions
    const transactions = await extractTransactions(apiGet);

    // Step 4: Download CSVs
    console.log('[Koinly Scraper] Downloading CSV files...');
    downloadCSV('koinly_wallets.csv', walletsToCSV(wallets));
    await sleep(1000);
    downloadCSV('koinly_transactions.csv', transactionsToCSV(transactions));

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    console.log('='.repeat(60));
    console.log(`[Koinly Scraper] Complete in ${elapsed}s`);
    console.log(`[Koinly Scraper] Wallets:      ${wallets.length}`);
    console.log(`[Koinly Scraper] Transactions: ${transactions.length}`);
    console.log('='.repeat(60));

    // Store data for debugging / further processing
    window.__koinlyData = { wallets, transactions, tokens };
    console.log('[Koinly Scraper] Data available at window.__koinlyData');

  } catch (error) {
    console.error('[Koinly Scraper] Fatal error:', error);
    console.error('[Koinly Scraper] Make sure you are logged into Koinly and on the Transactions page.');
  }
})();
